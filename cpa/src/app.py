"""
CPA FastAPI app.

Endpoints (all under the root path for simplicity; prefix with /cpa in
the ingress rather than here):

  GET  /health                    → health check
  POST /enroll                    → build/refresh a CPP-E for one user
  POST /score                     → score one email against the user's CPP
  GET  /cpp-status                → per-user CPP metadata and mirror state
  GET  /labeling-queue            → the card stack for the labeling UI
  POST /label                     → user writes/overrides a TW label
  GET  /labeling-progress         → summary stats

Design notes for next-Claude:
  - /enroll is synchronous for v1. It can take 30-120 seconds for a
    2000-email profile. Clients should use a long timeout. Phase 2 makes
    this async with a job_id + polling via /cpp-status.
  - /score must be fast (sub-500ms). It hits the in-memory CPP cache.
  - The app does NOT expose the mirror push endpoint; that's internal
    and the background task triggers it. See mirror.py (Phase 2).
  - No authentication in v1. The service runs inside the tenant's network
    boundary, behind their auth. If we ever expose it on the open internet
    that changes — tenant API keys + per-endpoint scopes.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from auto_classify import DirectoryEntry
from background_corpus import ensure_background_corpus
from config import LOG_LEVEL, SERVICE_NAME, SERVICE_VERSION
from db import connection, cpps as cpps_t, email_sha256, health_check, init_schema, mirror_state as mirror_t
from enrollment import RawEmail, enroll_user
from labels import get_labeling_queue, labeling_progress, set_label
from models import (
    CPPStatusRequest, CPPStatusResponse,
    EnrollRequest, EnrollResponse,
    HealthResponse,
    LabelingProgressResponse,
    LabelingQueueItem as LabelingQueueItemModel,
    LabelingQueueResponse,
    ScoreRequest, ScoreResponse,
    SetLabelRequest, SetLabelResponse,
)
from scoring import invalidate_cpp_cache, score_email

# ---- Logging setup -----------------------------------------------------

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# ---- App ---------------------------------------------------------------

app = FastAPI(
    title="CPA — Communication Personality Analyzer",
    version=SERVICE_VERSION,
    description=(
        "Builds per-user Communication Personality Profiles (CPPs) from "
        "email history and scores new emails against those profiles. "
        "First lens: the Classifier Lens consumed by Chimera Secured."
    ),
)


@app.on_event("startup")
def _startup() -> None:
    log.info("starting %s v%s", SERVICE_NAME, SERVICE_VERSION)
    init_schema()
    # Warm up the background corpus so the first enrollment doesn't stall.
    # If this fails (no DB, empty Enron), enrollments will fail with a
    # clear error message; we don't block startup on it.
    try:
        corpus = ensure_background_corpus()
        log.info("background corpus ready: %d texts", len(corpus))
    except Exception as e:
        log.error("background corpus init failed: %s (enrollments will fail)", e)


# ---- Health ------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    from background_corpus import BackgroundCorpus
    corpus = BackgroundCorpus.load()
    return HealthResponse(
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        db_healthy=health_check(),
        background_corpus_size=len(corpus),
    )


# ---- Enrollment --------------------------------------------------------

@app.post("/enroll", response_model=EnrollResponse)
def enroll(req: EnrollRequest) -> EnrollResponse:
    log.info(
        "enroll requested: tenant=%s user=%s raw_count=%d",
        req.tenant_id, req.user_id, len(req.emails),
    )

    # Build the directory map if provided
    directory: dict[str, DirectoryEntry] | None = None
    if req.directory:
        directory = {
            entry.email.strip().lower(): DirectoryEntry(
                email=entry.email,
                name=entry.name,
                is_internal=entry.is_internal,
                is_executive=entry.is_executive,
                department=entry.department,
            )
            for entry in req.directory
        }

    known_bd = set((req.known_business_domains or []))

    raw_emails = [
        RawEmail(recipient_email=e.recipient_email, body=e.body, sent_at=e.sent_at)
        for e in req.emails
    ]

    # Ensure a background corpus is available
    from background_corpus import BackgroundCorpus
    from config import MIN_EMAILS_FOR_HEAD
    corpus = BackgroundCorpus.load()
    if len(corpus) < MIN_EMAILS_FOR_HEAD:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Background corpus has {len(corpus)} texts "
                f"(need at least {MIN_EMAILS_FOR_HEAD}). "
                "Populate it via scripts/seed_background.py or set "
                "DATABASE_URL to a Postgres DB with the Enron corpus."
            ),
        )

    try:
        result = enroll_user(
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            user_email=req.user_email,
            raw_emails=raw_emails,
            directory=directory,
            background_corpus=corpus,
            known_business_domains=known_bd,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("enroll failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Enrollment failed: {e}")

    # Invalidate CPP cache so the next /score call loads the new artifact
    invalidate_cpp_cache()

    return EnrollResponse(
        cpp_version=result.cpp_version,
        content_hash=result.content_hash,
        training_email_count=result.training_email_count,
        tw_coverage=result.tw_coverage,
        buckets_trained=result.buckets_trained,
        buckets_skipped=result.buckets_skipped,
        recipient_count=result.recipient_count,
        message=(
            f"CPP-E built. Trained {len(result.buckets_trained)} bucket(s); "
            f"skipped {len(result.buckets_skipped)} due to insufficient data."
        ),
    )


# ---- Scoring -----------------------------------------------------------

@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    result = score_email(
        tenant_id=req.tenant_id,
        user_email=req.user_email,
        email_body=req.email_body,
        recipient_email=req.recipient_email,
    )
    return ScoreResponse(
        p_authentic=result.p_authentic,
        confidence=result.confidence,
        tw_bucket_used=result.tw_bucket_used,
        tw_source=result.tw_source,  # type: ignore[arg-type]
        cpp_version=result.cpp_version,
        reason=result.reason,
    )


# ---- CPP status --------------------------------------------------------

@app.get("/cpp-status", response_model=CPPStatusResponse)
def cpp_status(tenant_id: str, user_email: str) -> CPPStatusResponse:
    user_sha = email_sha256(user_email)

    with connection() as conn:
        cpp_row = conn.execute(
            select(cpps_t).where(
                (cpps_t.c.tenant_id == tenant_id) & (cpps_t.c.email_sha256 == user_sha)
            )
        ).first()
        mirror_row = conn.execute(
            select(mirror_t).where(
                (mirror_t.c.tenant_id == tenant_id) &
                (mirror_t.c.email_sha256 == user_sha)
            )
        ).first()

    if cpp_row is None:
        return CPPStatusResponse(exists=False)

    # tw_coverage_json is stored as a stringified dict; parse it loosely.
    import ast
    try:
        coverage = ast.literal_eval(cpp_row.tw_coverage_json or "{}")
    except Exception:
        coverage = {}

    return CPPStatusResponse(
        exists=True,
        cpp_version=cpp_row.cpp_version,
        content_hash=cpp_row.content_hash,
        training_email_count=cpp_row.training_email_count,
        tw_coverage=coverage,
        trained_at=cpp_row.trained_at.isoformat() if isinstance(cpp_row.trained_at, datetime) else str(cpp_row.trained_at),
        last_mirrored_hash=(mirror_row.last_mirrored_hash if mirror_row else None),
        last_mirrored_at=(
            mirror_row.last_mirrored_at.isoformat()
            if (mirror_row and mirror_row.last_mirrored_at)
            else None
        ),
    )


# ---- Labeling ---------------------------------------------------------

@app.get("/labeling-queue", response_model=LabelingQueueResponse)
def labeling_queue(
    tenant_id: str,
    user_id: str,
    limit: int = 50,
    only_unlabeled: bool = False,
) -> LabelingQueueResponse:
    items = get_labeling_queue(
        tenant_id=tenant_id,
        user_id=user_id,
        limit=limit,
        only_unlabeled=only_unlabeled,
    )
    return LabelingQueueResponse(
        items=[LabelingQueueItemModel(**i.__dict__) for i in items]
    )


@app.post("/label", response_model=SetLabelResponse)
def label(req: SetLabelRequest) -> SetLabelResponse:
    if req.bucket is None and req.fidelity is None:
        raise HTTPException(
            status_code=400,
            detail="Must provide either 'bucket' or 'fidelity'.",
        )
    try:
        item = set_label(
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            recipient_email=req.recipient_email,
            bucket=req.bucket,
            fidelity=req.fidelity,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SetLabelResponse(
        item=LabelingQueueItemModel(**item.__dict__),
        message=f"Label for {item.recipient_email} set to {item.current_bucket}.",
    )


@app.get("/labeling-progress", response_model=LabelingProgressResponse)
def progress(tenant_id: str, user_id: str) -> LabelingProgressResponse:
    return LabelingProgressResponse(**labeling_progress(tenant_id, user_id))
