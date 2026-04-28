"""
Enrollment orchestration.

Given a list of sent emails for a user, this module:

  1. Preprocesses and PII-scrubs every email.
  2. Groups emails by recipient.
  3. Auto-classifies each recipient to a default TW bucket.
  4. Assigns each email to its recipient's TW bucket → positive training pool.
  5. Samples a background corpus (negatives).
  6. Fits one FeatureExtractor on ALL positives (char n-gram vocab is shared).
  7. Trains one TWHead per bucket that has enough positives.
  8. Writes all artifacts to disk.
  9. Updates DB: cpps row, recipient_labels rows, mirror_state row.
 10. Computes content hash and optionally triggers mirror push.

This is the top-level flow that `/cpa/enroll` calls.

Design notes for next-Claude:
  - Enrollment is slow (minutes) for large corpora. The API endpoint should
    launch this as a background task and return a job_id; /cpa/cpp-status
    reports job state.
  - All three TW heads share ONE fitted FeatureExtractor. Different
    extractors per head would mean different feature spaces for different
    recipients, which breaks the "compare apples to apples" property
    during scoring.
  - If a bucket has fewer than MIN_EMAILS_FOR_HEAD positive examples, we
    skip it. Scoring falls back to the nearest available head.
  - Sent emails without a clear single recipient (e.g., 50 recipients in
    one To line — looks like a newsletter/blast) are excluded from training.
    We're modeling how this user writes to specific people.
"""
from __future__ import annotations

import json
import logging
import pickle
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select

from auto_classify import (
    DirectoryEntry,
    build_country_priors,
    classify_all,
    classify_recipient,
)
from background_corpus import BackgroundCorpus
from classifier import TWHead, TWPredictor
from config import (
    ARTIFACTS_DIR,
    BACKGROUND_SAMPLE_SIZE,
    MIN_EMAILS_FOR_HEAD,
    MIN_TRAIN_EMAIL_WORDS,
)
from db import cpps as cpps_t, email_sha256, mirror_state as mirror_t, recipient_labels as rl_t, transaction
from features import FeatureExtractor
from hashing import compute_cpp_hash
from pii_scrub import scrub
from preprocessing import preprocess
from voice_stats import compute_voice_stats

log = logging.getLogger(__name__)


@dataclass
class RawEmail:
    """One sent email as input to enrollment."""
    recipient_email: str
    body: str
    sent_at: str | None = None
    word_count: int | None = None  # filled in during preprocessing if None


@dataclass
class EnrollmentResult:
    cpp_version: str
    content_hash: str
    training_email_count: int
    tw_coverage: dict[str, int]  # bucket -> training example count
    buckets_trained: list[str]
    buckets_skipped: list[str]
    recipient_count: int


# ---- The flow ------------------------------------------------------------

def enroll_user(
    tenant_id: str,
    user_id: str,
    user_email: str,
    raw_emails: list[RawEmail],
    *,
    directory: dict[str, DirectoryEntry] | None = None,
    background_corpus: BackgroundCorpus,
    known_business_domains: set[str] | None = None,
    cpp_version: str | None = None,
) -> EnrollmentResult:
    """
    The full enrollment flow for one user. See module docstring.
    """
    cpp_version = cpp_version or f"v{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    user_sha = email_sha256(user_email)
    log.info(
        "enroll_user: tenant=%s user=%s sha=%s raw_count=%d",
        tenant_id, user_id, user_sha[:12], len(raw_emails),
    )

    # ---- Step 1: preprocess every email --------------------------------

    cleaned: list[tuple[RawEmail, str]] = []
    for email in raw_emails:
        body, _meta = preprocess(email.body, min_words_to_keep=MIN_TRAIN_EMAIL_WORDS)
        body = scrub(body)
        if not body or len(body.split()) < MIN_TRAIN_EMAIL_WORDS:
            continue
        email.word_count = len(body.split())
        cleaned.append((email, body))
    log.info("enroll_user: after preprocess+scrub: %d emails", len(cleaned))

    if len(cleaned) < MIN_EMAILS_FOR_HEAD:
        raise ValueError(
            f"Not enough usable emails after preprocessing: "
            f"{len(cleaned)} < {MIN_EMAILS_FOR_HEAD}"
        )

    # ---- Step 2: group by recipient + compute send volumes --------------

    by_recipient: dict[str, list[tuple[RawEmail, str]]] = {}
    for email, body in cleaned:
        r = (email.recipient_email or "").strip().lower()
        if not r or "@" not in r:
            continue
        by_recipient.setdefault(r, []).append((email, body))

    # ---- Step 3: auto-classify each recipient --------------------------

    # Build the country-priors map from sent history BEFORE classifying,
    # since classification uses it.
    sent_for_priors = [
        {"recipient_email": email.recipient_email, "word_count": email.word_count or 0}
        for email, _ in cleaned
    ]
    country_priors = build_country_priors(sent_for_priors)

    recipient_rows = [
        {"recipient_email": r, "email_count": len(es)} for r, es in by_recipient.items()
    ]
    classifications = classify_all(
        recipient_rows,
        directory=directory,
        country_priors=country_priors,
        known_business_domains=known_business_domains,
    )
    cls_by_email = {c.recipient_email: c for c in classifications}

    # ---- Step 4: assign emails to TW buckets ---------------------------

    bucket_texts: dict[str, list[str]] = {"TW_PLUS": [], "TW_ZERO": [], "TW_MINUS": []}
    for r, entries in by_recipient.items():
        cls = cls_by_email.get(r)
        if cls is None:
            continue
        for _email, body in entries:
            bucket_texts[cls.tw_bucket].append(body)

    coverage = {b: len(v) for b, v in bucket_texts.items()}
    log.info("enroll_user: tw_coverage=%s", coverage)

    # ---- Step 5: fit FeatureExtractor on ALL positives ------------------

    all_positives = bucket_texts["TW_MINUS"] + bucket_texts["TW_ZERO"] + bucket_texts["TW_PLUS"]
    extractor = FeatureExtractor().fit(all_positives)
    log.info("enroll_user: extractor feature_dim=%d", extractor.feature_dim)

    # ---- Step 6: sample background corpus ------------------------------

    if len(background_corpus) < MIN_EMAILS_FOR_HEAD:
        raise ValueError(
            f"Background corpus too small: {len(background_corpus)} "
            f"(need at least {MIN_EMAILS_FOR_HEAD})"
        )
    neg_sample_size = min(BACKGROUND_SAMPLE_SIZE, len(background_corpus))
    negatives = background_corpus.sample(neg_sample_size)

    # ---- Step 7: train each TW head that has enough data ----------------

    buckets_trained: list[str] = []
    buckets_skipped: list[str] = []
    heads: dict[str, TWHead] = {}
    for bucket, texts in bucket_texts.items():
        if len(texts) < MIN_EMAILS_FOR_HEAD:
            buckets_skipped.append(bucket)
            log.info("enroll_user: skipping %s (only %d examples)", bucket, len(texts))
            continue
        head = TWHead(bucket, extractor)
        head.fit(texts, negatives)
        heads[bucket] = head
        buckets_trained.append(bucket)

    if not heads:
        raise ValueError(
            "No TW bucket has enough training examples. "
            "User needs more sent emails, or auto-classification is funneling "
            "them all to one bucket."
        )

    # ---- Step 8: build the TW predictor --------------------------------

    predictor = TWPredictor()
    for cls in classifications:
        predictor.set_label(cls.recipient_email, cls.tw_bucket, source="auto")

    # ---- Step 8b: compute voice stats for exportable style guide --------

    all_training_texts = [body for _email, body in cleaned]
    voice_stats_data = compute_voice_stats(all_training_texts)
    log.info("enroll_user: voice_stats computed (%d emails)", voice_stats_data.get("email_count", 0))

    # ---- Step 9: write artifacts to disk -------------------------------

    art_root = ARTIFACTS_DIR / tenant_id / user_sha / cpp_version
    art_root.mkdir(parents=True, exist_ok=True)

    extractor_path = art_root / "extractor.pkl"
    with extractor_path.open("wb") as f:
        pickle.dump(extractor, f)

    head_paths: dict[str, Path] = {}
    for bucket, head in heads.items():
        p = art_root / f"head_{bucket.lower()}.pkl"
        head.save(p)
        head_paths[bucket] = p

    tw_predictor_path = art_root / "tw_predictor.pkl"
    predictor.save(tw_predictor_path)

    voice_stats_path = art_root / "voice_stats.json"
    with voice_stats_path.open("w") as f:
        json.dump(voice_stats_data, f, indent=2)

    # ---- Step 10: compute content hash ---------------------------------

    content_hash = compute_cpp_hash(
        head_paths=head_paths,
        extractor_path=extractor_path,
        tw_predictor_path=tw_predictor_path,
        label_map={c.recipient_email: (c.tw_bucket, "auto") for c in classifications},
        meta={
            "training_email_count": len(cleaned),
            "tw_coverage": coverage,
            "format_version": "1.0",
        },
    )
    log.info("enroll_user: content_hash=%s", content_hash[:16])

    # ---- Step 11: persist to DB ---------------------------------------

    now = datetime.now(timezone.utc)

    with transaction() as conn:
        # Remove prior rows for this (tenant_id, user_id); enrollment is
        # replace-on-run for v1. Incremental refresh is Phase 2.
        conn.execute(delete(cpps_t).where(
            (cpps_t.c.tenant_id == tenant_id) & (cpps_t.c.user_id == user_id)
        ))
        conn.execute(delete(rl_t).where(
            (rl_t.c.tenant_id == tenant_id) & (rl_t.c.user_id == user_id)
        ))

        # Insert CPP row
        conn.execute(cpps_t.insert().values(
            tenant_id=tenant_id,
            user_id=user_id,
            email_sha256=user_sha,
            cpp_version=cpp_version,
            content_hash=content_hash,
            head_tw_minus_path=str(head_paths.get("TW_MINUS", "")) or None,
            head_tw_zero_path=str(head_paths.get("TW_ZERO", "")) or None,
            head_tw_plus_path=str(head_paths.get("TW_PLUS", "")) or None,
            tw_predictor_path=str(tw_predictor_path),
            feature_config_path=str(extractor_path),
            voice_stats_path=str(voice_stats_path),
            training_email_count=len(cleaned),
            tw_coverage_json=json.dumps(coverage),
            trained_at=now,
            created_at=now,
            updated_at=now,
        ))

        # Insert recipient_labels rows
        vol_by_r = {r: len(es) for r, es in by_recipient.items()}
        for cls in classifications:
            conn.execute(rl_t.insert().values(
                tenant_id=tenant_id,
                user_id=user_id,
                recipient_email=cls.recipient_email,
                recipient_name=None,
                tw_bucket=cls.tw_bucket,
                tw_fidelity=None,
                label_source="auto",
                confidence=cls.confidence,
                auto_rule=cls.auto_rule,
                needs_review=int(cls.needs_review),
                email_count=vol_by_r.get(cls.recipient_email, 0),
                created_at=now,
                updated_at=now,
            ))

        # Upsert mirror_state (hash differs from last mirror → next mirror push will fire)
        existing = conn.execute(
            select(mirror_t).where(
                (mirror_t.c.tenant_id == tenant_id) &
                (mirror_t.c.user_id == user_id)
            )
        ).first()
        if existing is None:
            conn.execute(mirror_t.insert().values(
                tenant_id=tenant_id,
                user_id=user_id,
                email_sha256=user_sha,
                last_mirrored_hash=None,
                last_mirrored_at=None,
                last_heartbeat_at=None,
                mirror_enabled=1,
            ))
        # else: leave last_mirrored_hash untouched. The mirror client will
        # compare it to the new content_hash and push if they differ.

    log.info(
        "enroll_user: done tenant=%s user=%s buckets=%s hash=%s",
        tenant_id, user_id, buckets_trained, content_hash[:12],
    )
    return EnrollmentResult(
        cpp_version=cpp_version,
        content_hash=content_hash,
        training_email_count=len(cleaned),
        tw_coverage=coverage,
        buckets_trained=buckets_trained,
        buckets_skipped=buckets_skipped,
        recipient_count=len(classifications),
    )
