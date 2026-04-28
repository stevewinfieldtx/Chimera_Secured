"""
Pydantic models for the CPA HTTP API.

Every endpoint has a matching Request + Response pair so OpenAPI docs are
accurate and clients can codegen off the schema.

Design notes for next-Claude:
  - Email bodies in /enroll and /score are strings, NOT base64 or encrypted.
    These endpoints are called from inside the tenant boundary - the body
    is already in the caller's process. If we ever expose /score to the
    public internet, re-evaluate whether to encrypt-at-rest in transit;
    for v1, TLS is enough because the scorer is tenant-local.
  - We use Pydantic v2 syntax (Field, model_validator).
  - Timestamps are ISO 8601 strings in responses. Inputs accept either
    string or datetime.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---- Common ------------------------------------------------------------

class HealthResponse(BaseModel):
    service: str
    version: str
    db_healthy: bool
    background_corpus_size: int


# ---- Enrollment ---------------------------------------------------------

class EnrollEmail(BaseModel):
    """One sent email as input to enrollment. Body is preprocessed and
    discarded; only features persist."""
    recipient_email: str
    body: str
    sent_at: str | None = None


class EnrollDirectoryEntry(BaseModel):
    """Optional directory entry; if provided, used by auto-classification."""
    email: str
    name: str | None = None
    is_internal: bool = True
    is_executive: bool = False
    department: str | None = None


class EnrollRequest(BaseModel):
    tenant_id: str
    user_id: str = Field(
        ...,
        description=(
            "Tenant-scoped user identifier. For the dev path we use the "
            "SHA256-16 of the user's email; in production the tenant "
            "passes its own ID."
        ),
    )
    user_email: str
    emails: list[EnrollEmail] = Field(
        ...,
        description="The user's sent emails to profile from.",
    )
    directory: list[EnrollDirectoryEntry] | None = Field(
        default=None,
        description="Optional M365-style directory for auto-classification.",
    )
    known_business_domains: list[str] | None = None


class EnrollResponse(BaseModel):
    cpp_version: str
    content_hash: str
    training_email_count: int
    tw_coverage: dict[str, int]
    buckets_trained: list[str]
    buckets_skipped: list[str]
    recipient_count: int
    message: str


# ---- Scoring ------------------------------------------------------------

class ScoreRequest(BaseModel):
    tenant_id: str
    user_email: str
    recipient_email: str
    email_body: str


class ScoreResponse(BaseModel):
    p_authentic: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    tw_bucket_used: str
    tw_source: Literal["labeled", "auto", "fallback_zero", "no_cpp", "empty"]
    cpp_version: str
    reason: str


# ---- CPP status --------------------------------------------------------

class CPPStatusRequest(BaseModel):
    tenant_id: str
    user_email: str


class CPPStatusResponse(BaseModel):
    exists: bool
    cpp_version: str | None = None
    content_hash: str | None = None
    training_email_count: int | None = None
    tw_coverage: dict[str, int] | None = None
    trained_at: str | None = None
    last_mirrored_hash: str | None = None
    last_mirrored_at: str | None = None


# ---- Labeling ----------------------------------------------------------

class LabelingQueueItem(BaseModel):
    recipient_email: str
    recipient_name: str | None = None
    current_bucket: str
    current_fidelity: str | None = None
    label_source: str
    auto_rule: str | None = None
    needs_review: bool
    email_count: int


class LabelingQueueResponse(BaseModel):
    items: list[LabelingQueueItem]


class SetLabelRequest(BaseModel):
    tenant_id: str
    user_id: str
    recipient_email: str
    # Exactly one of these must be provided.
    bucket: Literal["TW_PLUS", "TW_ZERO", "TW_MINUS"] | None = None
    fidelity: Literal[
        "TW+9", "TW+6", "TW+3", "TW0", "TW-3", "TW-6", "TW-9",
    ] | None = None


class SetLabelResponse(BaseModel):
    item: LabelingQueueItem
    message: str


class LabelingProgressResponse(BaseModel):
    total_recipients: int
    user_labeled: int
    auto_labeled: int
    flagged_for_review: int


# ---- Voice profile -------------------------------------------------------

class VoiceProfileSection(BaseModel):
    number: int
    title: str
    emoji: str
    body: str


class VoiceProfileResponse(BaseModel):
    exists: bool
    formality_score: float | None = None
    email_count: int | None = None
    summary: str | None = None
    sections: list[VoiceProfileSection] | None = None
    prompt_text: str | None = Field(
        default=None,
        description="Full profile as copy-pasteable text for use in other LLMs.",
    )
    markdown: str | None = None


# ---- Graph-based enrollment ----------------------------------------------

class GraphEnrollRequest(BaseModel):
    """Enroll a user by pulling their sent mail directly from Graph API."""
    tenant_id: str = "default"
    user_email: str
    max_emails: int = 2000


class GraphEnrollResponse(BaseModel):
    status: str
    user_email: str
    emails_fetched: int = 0
    cpp_version: str | None = None
    content_hash: str | None = None
    training_email_count: int | None = None
    message: str
