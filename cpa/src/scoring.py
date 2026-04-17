"""
Scoring.

Given (email_body, inbox_owner, recipient), return p_authentic: the
probability that the email was actually written by the inbox owner.

Flow:
  1. Load the user's CPP-E (extractor + TW heads + predictor) from disk.
  2. Preprocess + PII-scrub the email body.
  3. Ask the TW predictor which bucket applies for this recipient.
  4. Score the email against that bucket's head.
  5. Handle missing-bucket fallbacks (if the predicted bucket has no head,
     fall back to TW_ZERO, then to whatever head exists).
  6. Return p_authentic, confidence, the bucket used, and a reason string.

Design notes for next-Claude:
  - CPPs are memory-mapped on first load and cached process-wide. Scoring
    is called many times per second; we cannot afford to re-unpickle per
    request. The cache is keyed by (tenant_id, user_id, cpp_version).
  - Short-email handling: emails below SHORT_EMAIL_WORDS produce a lowered
    confidence value. The Chimera Secured composer reads this and down-
    weights D1's contribution accordingly. The CPA itself still returns
    a probability.
  - If the user has no CPP, we return a sentinel (p_authentic=0.5,
    confidence=0.0). The scorer treats this as "no signal from D1."
"""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select

from classifier import TWHead, TWPredictor
from config import MIN_TRAIN_EMAIL_WORDS
from db import connection, cpps as cpps_t, email_sha256, recipient_labels as rl_t
from features import FeatureExtractor
from pii_scrub import scrub
from preprocessing import preprocess

log = logging.getLogger(__name__)

SHORT_EMAIL_WORDS = 15  # below this, confidence is reduced


@dataclass
class ScoreResult:
    p_authentic: float      # 0.0 (definitely not the user) - 1.0 (definitely the user)
    confidence: float       # 0.0 (no signal) - 1.0 (strong signal)
    tw_bucket_used: str     # which head actually scored the email
    tw_source: str          # how we chose the bucket: labeled/auto/fallback
    cpp_version: str
    reason: str


# ---- CPP loader + cache --------------------------------------------------

@dataclass
class LoadedCPP:
    cpp_version: str
    content_hash: str
    extractor: FeatureExtractor
    heads: dict[str, TWHead]        # bucket -> head (only loaded buckets)
    predictor: TWPredictor
    training_email_count: int


@lru_cache(maxsize=256)
def load_cpp(tenant_id: str, email_sha: str) -> LoadedCPP | None:
    """
    Load the current CPP-E for a user, keyed by tenant and the SHA-256 of
    their email address. Cached by (tenant_id, email_sha).

    We look up by email_sha256 rather than user_id because email_sha256 is
    the stable lookup alias that survives tenant-scoped user-id changes
    and matches what the Railway mirror uses.

    NOTE: cache invalidation is manual. When enrollment runs, the caller
    must invoke `invalidate_cpp_cache()` or the scorer will keep returning
    the old CPP. Enrollment does this automatically; external callers
    changing labels do NOT invalidate the cache because label changes
    don't affect cached artifacts (labels are read fresh from DB each
    score call via the predictor).

    See scoring.score_email for the refresh pattern.
    """
    with connection() as conn:
        row = conn.execute(
            select(cpps_t).where(
                (cpps_t.c.tenant_id == tenant_id) & (cpps_t.c.email_sha256 == email_sha)
            )
        ).first()
        if row is None:
            return None

        # Load extractor
        extractor = _load_pickle(Path(row.feature_config_path))

        # Load heads
        heads: dict[str, TWHead] = {}
        for bucket, col in (
            ("TW_MINUS", row.head_tw_minus_path),
            ("TW_ZERO", row.head_tw_zero_path),
            ("TW_PLUS", row.head_tw_plus_path),
        ):
            if col:
                heads[bucket] = TWHead.load(Path(col), extractor)

        # Load predictor
        predictor = TWPredictor.load(Path(row.tw_predictor_path))

        # Overlay user-set labels from DB (newer than the pickled predictor
        # snapshot). User swipes land in recipient_labels with
        # label_source='user' and we want those to win.
        user_labels = conn.execute(
            select(rl_t.c.recipient_email, rl_t.c.tw_bucket, rl_t.c.label_source).where(
                (rl_t.c.tenant_id == tenant_id) &
                (rl_t.c.user_id == row.user_id) &
                (rl_t.c.label_source == "user")
            )
        ).all()
        for email, bucket, source in user_labels:
            predictor.set_label(email, bucket, source="user")

    return LoadedCPP(
        cpp_version=row.cpp_version,
        content_hash=row.content_hash,
        extractor=extractor,
        heads=heads,
        predictor=predictor,
        training_email_count=row.training_email_count,
    )


def invalidate_cpp_cache(tenant_id: str | None = None, user_id: str | None = None) -> None:
    """Clear cached CPPs. Call after enrollment. Coarse-grained for v1."""
    load_cpp.cache_clear()


def _load_pickle(path: Path):
    with path.open("rb") as f:
        return pickle.load(f)


# ---- Score ---------------------------------------------------------------

def score_email(
    tenant_id: str,
    user_email: str,
    email_body: str,
    recipient_email: str,
) -> ScoreResult:
    """
    Score a new email against the user's CPP-E.

    `user_email` is the inbox owner (the person claimed to have sent this).
    `recipient_email` is who it was sent to.
    """
    # Look up by email_sha256 — the stable lookup alias that matches what
    # the Railway mirror uses.
    user_sha = email_sha256(user_email)

    cpp = load_cpp(tenant_id, user_sha)
    if cpp is None:
        return ScoreResult(
            p_authentic=0.5,
            confidence=0.0,
            tw_bucket_used="none",
            tw_source="no_cpp",
            cpp_version="none",
            reason="No CPP-E exists for this user. Enrollment required.",
        )

    # Preprocess + scrub
    cleaned, meta = preprocess(email_body, min_words_to_keep=MIN_TRAIN_EMAIL_WORDS)
    cleaned = scrub(cleaned)
    final_words = len(cleaned.split()) if cleaned else 0

    if final_words == 0:
        return ScoreResult(
            p_authentic=0.5,
            confidence=0.0,
            tw_bucket_used="none",
            tw_source="empty",
            cpp_version=cpp.cpp_version,
            reason="Email body empty after preprocessing.",
        )

    # Pick the TW bucket
    prediction = cpp.predictor.predict(recipient_email)
    chosen_bucket, fallback_reason = _resolve_bucket(prediction.bucket, cpp.heads)

    head = cpp.heads[chosen_bucket]
    p_authentic = float(head.predict_proba([cleaned])[0])

    # Confidence: based on bucket-selection source, head's training volume,
    # and whether the email is short.
    confidence = _compute_confidence(
        prediction_source=prediction.source,
        bucket_fallback=chosen_bucket != prediction.bucket,
        training_positive_count=head.metadata.training_positive_count if head.metadata else 0,
        final_words=final_words,
    )

    reason_parts = [prediction.reason]
    if chosen_bucket != prediction.bucket:
        reason_parts.append(fallback_reason)
    if final_words < SHORT_EMAIL_WORDS:
        reason_parts.append(
            f"Short email ({final_words} words); style signal is reduced."
        )

    return ScoreResult(
        p_authentic=p_authentic,
        confidence=confidence,
        tw_bucket_used=chosen_bucket,
        tw_source=prediction.source,
        cpp_version=cpp.cpp_version,
        reason=" ".join(reason_parts),
    )


def _resolve_bucket(
    predicted: str,
    heads: dict[str, TWHead],
) -> tuple[str, str]:
    """
    Return the actual bucket to score against, plus a reason if we had to
    fall back from the predicted one.

    Preference order: predicted → TW_ZERO → any available head.
    """
    if predicted in heads:
        return predicted, ""
    if "TW_ZERO" in heads:
        return "TW_ZERO", f"No head trained for {predicted}; falling back to TW_ZERO."
    # Last resort: any head at all
    any_bucket = next(iter(heads.keys()))
    return any_bucket, (
        f"No head trained for {predicted} and TW_ZERO is missing; "
        f"using {any_bucket} as a last resort."
    )


def _compute_confidence(
    prediction_source: str,
    bucket_fallback: bool,
    training_positive_count: int,
    final_words: int,
) -> float:
    """Heuristic confidence score on [0, 1]. Higher = more trustworthy."""
    conf = 0.5

    # Bucket-prediction source
    if prediction_source == "labeled":
        conf += 0.25
    elif prediction_source == "auto":
        conf += 0.10
    # fallback_zero / no_cpp: no bump

    # Bucket fallback penalty (asked for TW_PLUS, got TW_ZERO)
    if bucket_fallback:
        conf -= 0.10

    # Training volume (more = better)
    if training_positive_count >= 200:
        conf += 0.15
    elif training_positive_count >= 100:
        conf += 0.10
    elif training_positive_count >= 50:
        conf += 0.05

    # Short-email penalty
    if final_words < SHORT_EMAIL_WORDS:
        # Scale: 14 words = slight penalty, 5 words = heavy penalty.
        scale = max(0, (SHORT_EMAIL_WORDS - final_words)) / SHORT_EMAIL_WORDS
        conf -= 0.30 * scale

    return max(0.0, min(1.0, conf))
