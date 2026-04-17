"""
Database connection and schema.

Uses SQLAlchemy Core (not ORM) because the query surface is small and the
schema is stable — ORM would just add overhead and a second mental model.

Schema:
  - cpps: one row per (tenant_id, user_id). The CPP-E metadata record.
          Classifier artifacts live on disk; this table holds paths + hashes.
  - recipient_labels: one row per (tenant_id, user_id, recipient_email).
          Stores TW bucket + fidelity + source (auto/user) + confidence.
  - mirror_state: tracks what's been pushed to Railway.
          One row per CPP; updated on successful mirror push.
  - enrollment_jobs: tracks in-progress and completed enrollments.
          Enrollment is slow (minutes) so it runs async; this is the state.

Design notes for next-Claude:
  - Every write goes through a transaction. Reads can use the engine directly.
  - tenant_id + user_id is the composite key everywhere. email_sha256 is an
    additional lookup alias (computed, not primary) for the Railway mirror.
  - Artifact paths are stored relative to ARTIFACTS_DIR so we can move the
    data directory without breaking references.
"""
from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import (
    Column, DateTime, Float, Integer, MetaData, String, Table, Text,
    create_engine, text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from config import DATABASE_URL

log = logging.getLogger(__name__)

metadata = MetaData()

# ---- Tables -------------------------------------------------------------

cpps = Table(
    "cpps", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("user_id", String, nullable=False),
    Column("email_sha256", String, nullable=False, index=True),
    Column("cpp_version", String, nullable=False),
    Column("content_hash", String, nullable=False),
    # Artifact paths (relative to ARTIFACTS_DIR)
    Column("head_tw_minus_path", String, nullable=True),
    Column("head_tw_zero_path", String, nullable=True),
    Column("head_tw_plus_path", String, nullable=True),
    Column("tw_predictor_path", String, nullable=True),
    Column("feature_config_path", String, nullable=True),
    # Metadata
    Column("training_email_count", Integer, nullable=False, default=0),
    Column("tw_coverage_json", Text, nullable=True),  # {"TW_PLUS": 42, ...}
    Column("trained_at", DateTime, nullable=False),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

recipient_labels = Table(
    "recipient_labels", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("user_id", String, nullable=False),
    Column("recipient_email", String, nullable=False),
    Column("recipient_name", String, nullable=True),
    # TW label
    Column("tw_bucket", String, nullable=False),  # TW_PLUS / TW_ZERO / TW_MINUS
    Column("tw_fidelity", String, nullable=True),  # TW+3 / TW+6 / TW+9 / TW0 / TW-3 / ...
    Column("label_source", String, nullable=False),  # 'auto' or 'user'
    Column("confidence", Float, nullable=False, default=0.5),
    # Auto-classification signal
    Column("auto_rule", String, nullable=True),  # 'consumer_domain' / 'internal_exec' / etc.
    Column("needs_review", Integer, nullable=False, default=0),  # bool as int for sqlite compat
    Column("email_count", Integer, nullable=False, default=0),
    # Audit
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

mirror_state = Table(
    "mirror_state", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String, nullable=False),
    Column("user_id", String, nullable=False),
    Column("email_sha256", String, nullable=False),
    Column("last_mirrored_hash", String, nullable=True),
    Column("last_mirrored_at", DateTime, nullable=True),
    Column("last_heartbeat_at", DateTime, nullable=True),
    Column("mirror_enabled", Integer, nullable=False, default=1),  # bool
    Column("last_error", Text, nullable=True),
)

enrollment_jobs = Table(
    "enrollment_jobs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("job_id", String, nullable=False, unique=True, index=True),
    Column("tenant_id", String, nullable=False),
    Column("user_id", String, nullable=False),
    Column("email_sha256", String, nullable=False),
    Column("status", String, nullable=False),  # pending/running/done/failed
    Column("emails_processed", Integer, nullable=False, default=0),
    Column("started_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("finished_at", DateTime, nullable=True),
    Column("error", Text, nullable=True),
)

# ---- Engine management --------------------------------------------------

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is not None:
        return _engine

    connect_args = {}
    kwargs = {}
    if DATABASE_URL.startswith("sqlite"):
        # StaticPool + check_same_thread=False so FastAPI's thread pool can
        # share the connection. Fine for tenant-local SQLite.
        connect_args["check_same_thread"] = False
        kwargs["poolclass"] = StaticPool

    _engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True, **kwargs)
    log.info("db engine created: %s", DATABASE_URL.split("://")[0])
    return _engine


def init_schema() -> None:
    """Create all tables if they don't exist. Idempotent."""
    engine = get_engine()
    metadata.create_all(engine)
    log.info("schema initialized")


@contextmanager
def transaction() -> Iterator:
    """Context manager for transactional writes."""
    engine = get_engine()
    with engine.begin() as conn:
        yield conn


def connection():
    """Non-transactional connection context manager for reads."""
    engine = get_engine()
    return engine.connect()


# ---- Utility helpers ----------------------------------------------------

def email_sha256(email: str) -> str:
    """Canonical email-to-sha256 hash. Lowercase + strip before hashing."""
    normalized = email.strip().lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def health_check() -> bool:
    """Return True if the DB is reachable."""
    try:
        with connection() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.error("db health check failed: %s", e)
        return False
