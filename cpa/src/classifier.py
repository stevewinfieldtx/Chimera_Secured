"""
Classifier heads and TW predictor.

Two things in this module:

  1. `TWHead` — a single calibrated XGBoost classifier trained to separate
     the user's writing in ONE TW bucket (formal / average / casual) from
     the background corpus. Each user's CPP-E has up to three of these,
     one per bucket. Heads only exist for buckets that had enough training
     emails (see MIN_EMAILS_FOR_HEAD).

  2. `TWPredictor` — a classifier that, given a recipient's labeled bucket
     plus optional context, returns which head to use at scoring time.
     For v1 this is mostly a lookup against the recipient_labels table
     with a small fallback: if the recipient is unlabeled, predict based
     on domain + auto-classification rules. Not really ML; a rules engine
     wearing an ML-shaped hat.

Design notes for next-Claude:
  - Why XGBoost instead of logistic regression: on stylometric feature
    vectors with n=200-500 training samples, trees beat linear models.
    max_depth=3 keeps them from overfitting. The CPA white paper specifies
    XGBoost with calibrated probabilities; we're matching that.
  - Why CalibratedClassifierCV: raw XGBoost probabilities are not
    well-calibrated. Platt scaling via sigmoid calibration makes P(authentic)
    actually mean what it says. This matters because the Chimera Secured
    composer multiplies it by a content-category prior, and the math only
    works if the input is a real probability.
  - A head returns p_authentic, not p_fake. The scorer flips it at the
    composer boundary.
"""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix, vstack
from sklearn.calibration import CalibratedClassifierCV
from xgboost import XGBClassifier

from config import (
    CALIBRATION_CV_FOLDS,
    CALIBRATION_METHOD,
    MIN_EMAILS_FOR_HEAD,
    XGB_PARAMS,
)
from features import FeatureExtractor

log = logging.getLogger(__name__)


# ---- TWHead --------------------------------------------------------------

@dataclass
class TWHeadMetadata:
    bucket: str               # "TW_PLUS" / "TW_ZERO" / "TW_MINUS"
    training_positive_count: int
    training_negative_count: int
    feature_dim: int
    self_consistency_auc: float  # measured during fit via CV
    fitted_at: str               # isoformat


class TWHead:
    """
    One calibrated classifier trained on the user's writing in one TW bucket.

    Lifecycle:
        head = TWHead("TW_PLUS", extractor)
        head.fit(user_positive_texts, background_texts)
        p_authentic = head.predict_proba([new_email_text])[0]
    """

    def __init__(self, bucket: str, extractor: FeatureExtractor):
        self.bucket = bucket
        self.extractor = extractor
        self.model: CalibratedClassifierCV | None = None
        self.metadata: TWHeadMetadata | None = None

    def fit(self, positive_texts: list[str], negative_texts: list[str]) -> None:
        from datetime import datetime, timezone

        if len(positive_texts) < MIN_EMAILS_FOR_HEAD:
            raise ValueError(
                f"TW head '{self.bucket}' requires at least {MIN_EMAILS_FOR_HEAD} "
                f"positive examples; got {len(positive_texts)}"
            )

        X_pos = self.extractor.transform(positive_texts)
        X_neg = self.extractor.transform(negative_texts)
        X = vstack([X_pos, X_neg]).tocsr()
        y = np.concatenate([
            np.ones(X_pos.shape[0], dtype=np.int32),
            np.zeros(X_neg.shape[0], dtype=np.int32),
        ])

        # Determine a safe CV fold count. CalibratedClassifierCV needs at
        # least `cv` positives; with small datasets we scale down.
        cv = min(CALIBRATION_CV_FOLDS, len(positive_texts), len(negative_texts))
        cv = max(cv, 2)

        base = XGBClassifier(**XGB_PARAMS)
        calibrated = CalibratedClassifierCV(base, method=CALIBRATION_METHOD, cv=cv)
        calibrated.fit(X, y)
        self.model = calibrated

        # Self-consistency check: use cross-val predictions to estimate AUC
        # on training data. Not held-out, so treat as an upper bound on
        # actual performance — but useful as a sanity check during enrollment.
        # We approximate this by computing AUC on the training data against
        # the fitted model. Real performance is measured via the Enron eval.
        from sklearn.metrics import roc_auc_score
        try:
            proba = calibrated.predict_proba(X)[:, 1]
            self_auc = float(roc_auc_score(y, proba))
        except Exception:
            self_auc = 0.0

        self.metadata = TWHeadMetadata(
            bucket=self.bucket,
            training_positive_count=len(positive_texts),
            training_negative_count=len(negative_texts),
            feature_dim=self.extractor.feature_dim,
            self_consistency_auc=self_auc,
            fitted_at=datetime.now(timezone.utc).isoformat(),
        )
        log.info(
            "TWHead fit: bucket=%s pos=%d neg=%d self_auc=%.3f",
            self.bucket, len(positive_texts), len(negative_texts), self_auc,
        )

    def predict_proba(self, texts: list[str]) -> np.ndarray:
        """Return p_authentic for each text as a 1-D array."""
        if self.model is None:
            raise RuntimeError("TWHead.predict_proba called before fit")
        X = self.extractor.transform(texts)
        return self.model.predict_proba(X)[:, 1]

    # ---- Persistence ----------------------------------------------------

    def save(self, path: Path) -> None:
        """Pickle the head (model + metadata; NOT the extractor) to disk."""
        if self.model is None:
            raise RuntimeError("TWHead.save called before fit")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(
                {
                    "bucket": self.bucket,
                    "model": self.model,
                    "metadata": self.metadata,
                },
                f,
            )

    @classmethod
    def load(cls, path: Path, extractor: FeatureExtractor) -> "TWHead":
        with path.open("rb") as f:
            data = pickle.load(f)
        head = cls(data["bucket"], extractor)
        head.model = data["model"]
        head.metadata = data["metadata"]
        return head


# ---- TWPredictor ---------------------------------------------------------

@dataclass
class TWPrediction:
    bucket: str               # predicted bucket
    confidence: float         # 0.0 - 1.0
    source: str               # "labeled" / "auto" / "fallback_zero"
    reason: str


class TWPredictor:
    """
    Given a recipient email (and optional context), predict which TW bucket
    to score against.

    Priority:
      1. If the recipient has a user-set label in recipient_labels, use it.
      2. If the recipient has an auto-classification label, use it.
      3. Fall back to TW_ZERO with low confidence.

    This class is intentionally thin. The "heavy lifting" (auto-classification
    rules, directory lookups) lives in auto_classify.py. TWPredictor is
    mostly a wrapper that DB-backed callers hold and invoke at scoring time.

    Lifecycle:
        predictor = TWPredictor()
        # During enrollment / label updates:
        predictor.set_label("bob@acme.com", "TW_PLUS", source="user")
        # At scoring time:
        pred = predictor.predict("bob@acme.com")
        # Use pred.bucket to pick which head to score against.
    """

    def __init__(self):
        # In-memory label cache. The persistent version lives in recipient_labels
        # table; the enrollment flow loads this dict from DB at startup.
        self._labels: dict[str, tuple[str, str]] = {}  # email -> (bucket, source)

    def set_label(self, recipient_email: str, bucket: str, source: str = "auto") -> None:
        if bucket not in ("TW_PLUS", "TW_ZERO", "TW_MINUS"):
            raise ValueError(f"unknown bucket: {bucket}")
        if source not in ("user", "auto"):
            raise ValueError(f"unknown source: {source}")
        self._labels[recipient_email.strip().lower()] = (bucket, source)

    def load_from_dict(self, labels: dict[str, tuple[str, str]]) -> None:
        """Bulk load. Used on startup from the recipient_labels table."""
        for k, v in labels.items():
            self._labels[k.strip().lower()] = v

    def predict(self, recipient_email: str) -> TWPrediction:
        key = (recipient_email or "").strip().lower()
        hit = self._labels.get(key)
        if hit is not None:
            bucket, source = hit
            return TWPrediction(
                bucket=bucket,
                confidence=(0.85 if source == "user" else 0.65),
                source=("labeled" if source == "user" else "auto"),
                reason=f"{source}-assigned label for this recipient.",
            )
        return TWPrediction(
            bucket="TW_ZERO",
            confidence=0.40,
            source="fallback_zero",
            reason="No label for this recipient; defaulting to TW_ZERO.",
        )

    # ---- Persistence ----------------------------------------------------

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"labels": self._labels}, f)

    @classmethod
    def load(cls, path: Path) -> "TWPredictor":
        predictor = cls()
        with path.open("rb") as f:
            data = pickle.load(f)
        predictor._labels = data["labels"]
        return predictor
