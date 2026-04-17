"""
CPA configuration.

All runtime config comes from environment variables, with reasonable defaults
for local development. See `.env.example` at the repo root for the full list.

Design notes for next-Claude:
- Default DB is SQLite so this runs locally with zero setup. Production
  deployments set DATABASE_URL to a Postgres URL.
- Background corpus path defaults to a location we'll populate from the
  Enron DB; see background_corpus.py for how it gets built.
- All TW-related constants live here so the scoring gates can reference them.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---- Service identity ---------------------------------------------------

SERVICE_NAME = "cpa"
SERVICE_VERSION = "0.1.0"

# ---- Storage ------------------------------------------------------------

# Tenant-local DB. Default is SQLite in the data dir; override to Postgres
# via DATABASE_URL env for production.
DATA_DIR = Path(os.environ.get("CPA_DATA_DIR", "./cpa_data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{DATA_DIR / 'cpa.db'}",
)

# Where fitted classifier artifacts live on disk. Keeping these as files
# (not BLOBs in the DB) because they can be 1-10MB each and we want them
# memory-mapped for fast load at scoring time.
ARTIFACTS_DIR = Path(os.environ.get("CPA_ARTIFACTS_DIR", DATA_DIR / "artifacts"))
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

# ---- Enrollment --------------------------------------------------------

# Cap on how many sent emails we'll pull during enrollment. More is better
# up to a point (diminishing returns past ~2000).
MAX_ENROLL_EMAILS = int(os.environ.get("CPA_MAX_ENROLL_EMAILS", "2000"))

# Minimum emails to build any classifier head at all.
MIN_EMAILS_FOR_HEAD = int(os.environ.get("CPA_MIN_EMAILS_FOR_HEAD", "30"))

# Emails shorter than this are excluded from training — too little signal.
MIN_TRAIN_EMAIL_WORDS = 15

# ---- TW system ---------------------------------------------------------

# Three-bucket TW for v1. Nine-level UI labels collapse to these at
# scoring time; see labels.py.
TW_BUCKETS = ("TW_MINUS", "TW_ZERO", "TW_PLUS")

# Mapping from UI nine-level labels to v1 three-bucket.
TW_FIDELITY_TO_BUCKET = {
    "TW+9": "TW_PLUS", "TW+6": "TW_PLUS", "TW+3": "TW_PLUS",
    "TW0": "TW_ZERO",
    "TW-3": "TW_MINUS", "TW-6": "TW_MINUS", "TW-9": "TW_MINUS",
}

# ---- Auto-classification rules ------------------------------------------

# Free consumer email providers. Recipients at these domains default to TW-
# (casual) with a review flag. See auto_classify.py.
CONSUMER_DOMAINS = frozenset({
    "gmail.com", "googlemail.com",
    "hotmail.com", "outlook.com", "live.com", "msn.com",
    "yahoo.com", "yahoo.co.uk", "ymail.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com",
    "proton.me", "protonmail.com",
    "gmx.com", "gmx.de",
    "mail.com",
    "zoho.com",
    "fastmail.com",
})

# ---- Feature extraction -------------------------------------------------

# Character n-gram range. 3-5 is the sweet spot from the stylometry
# literature and matches what the CPA white paper describes.
CHAR_NGRAM_RANGE = (3, 5)
CHAR_NGRAM_MAX_FEATURES = 2000

# Function words: topic-independent markers of unconscious usage patterns.
# The list is the standard ~150-word lexicon used across stylometric work.
# Loaded from data file at runtime; see features.py.

# ---- Classifier training ------------------------------------------------

# XGBoost hyperparameters. Kept intentionally conservative — a deeper tree
# would overfit given that our training sets per head can be as small as 30.
XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 3,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "eval_metric": "logloss",
}

# Calibration method. Platt scaling ("sigmoid") is the standard choice for
# small datasets; isotonic needs more data to be stable.
CALIBRATION_METHOD = "sigmoid"
CALIBRATION_CV_FOLDS = 3

# ---- Background corpus -------------------------------------------------

# Where the pickled background feature set lives. Built by background_corpus.py
# from the Enron DB plus LLM-generated diverse writing.
BACKGROUND_CORPUS_PATH = Path(
    os.environ.get(
        "CPA_BACKGROUND_CORPUS",
        DATA_DIR / "background_corpus.pkl",
    )
)

# Size of the background corpus to sample against the target's positives
# during classifier training. Too few → classifier learns English instead
# of the user. Too many → training is slow.
BACKGROUND_SAMPLE_SIZE = 500

# ---- Mirror (Railway push) ----------------------------------------------

# Where to push CPP-E snapshots on content-hash change. Empty = mirroring
# disabled, CPP stays purely local.
MIRROR_URL = os.environ.get("CPA_MIRROR_URL", "").strip()
MIRROR_API_KEY = os.environ.get("CPA_MIRROR_API_KEY", "").strip()

# Heartbeat cadence. Plan says weekly.
HEARTBEAT_INTERVAL_DAYS = 7

# ---- Logging ------------------------------------------------------------

LOG_LEVEL = os.environ.get("CPA_LOG_LEVEL", "INFO").upper()
