"""
Labeling queue and user label write-back.

Two things in this module:

  1. `get_labeling_queue()` — returns the recipient list the user should
     label next, ordered by needs_review (flagged first) and by email_count
     (high-volume recipients first). This is what the PWA's card stack
     reads from.

  2. `set_label()` — persists a user's TW label for a recipient. Accepts
     either a coarse bucket (TW_PLUS/TW_ZERO/TW_MINUS) or a nine-level
     fidelity label (TW+3/+6/+9/-3/-6/-9/0) which gets collapsed to the
     bucket at write time for v1.

Design notes for next-Claude:
  - Labels don't invalidate the CPP cache — the scorer's load_cpp overlays
    user-set labels from DB on top of the pickled predictor each time it
    loads. So swipes take effect on the NEXT time the CPP is loaded, which
    is at most CPP_CACHE_TTL seconds later.
  - For v1 we collapse nine-level to three-level at write time. Storing
    the fidelity label is kept for Phase 2 when we use the nine-level
    scale directly at scoring time.
  - Labels don't trigger re-training. They change which head runs for a
    given recipient. That's it. Retraining is only needed if enough new
    emails arrive that the underlying head's training data would change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, select, update

from config import TW_FIDELITY_TO_BUCKET
from db import recipient_labels as rl_t, transaction


@dataclass
class LabelingQueueItem:
    recipient_email: str
    recipient_name: str | None
    current_bucket: str
    current_fidelity: str | None
    label_source: str        # 'auto' / 'user'
    auto_rule: str | None
    needs_review: bool
    email_count: int


def get_labeling_queue(
    tenant_id: str,
    user_id: str,
    *,
    limit: int = 50,
    only_unlabeled: bool = False,
) -> list[LabelingQueueItem]:
    """
    Return the next N recipients the user should label.

    Ordering:
      1. needs_review=True first (consumer-domain + unknown buckets)
      2. Within that, label_source='auto' before 'user' (user labels are
         already locked in and only need review if explicitly requested)
      3. By email_count descending (high-volume recipients first)
    """
    from db import connection

    q = (
        select(rl_t)
        .where((rl_t.c.tenant_id == tenant_id) & (rl_t.c.user_id == user_id))
    )
    if only_unlabeled:
        q = q.where(rl_t.c.label_source == "auto")

    q = q.order_by(
        rl_t.c.needs_review.desc(),
        rl_t.c.label_source.asc(),  # 'auto' < 'user' lexically, so auto first
        rl_t.c.email_count.desc(),
    ).limit(limit)

    with connection() as conn:
        rows = conn.execute(q).all()

    return [
        LabelingQueueItem(
            recipient_email=row.recipient_email,
            recipient_name=row.recipient_name,
            current_bucket=row.tw_bucket,
            current_fidelity=row.tw_fidelity,
            label_source=row.label_source,
            auto_rule=row.auto_rule,
            needs_review=bool(row.needs_review),
            email_count=row.email_count,
        )
        for row in rows
    ]


def set_label(
    tenant_id: str,
    user_id: str,
    recipient_email: str,
    *,
    bucket: str | None = None,
    fidelity: str | None = None,
) -> LabelingQueueItem:
    """
    Persist a user label. Provide either `bucket` (TW_PLUS/TW_ZERO/TW_MINUS)
    or `fidelity` (TW+3/TW+6/TW+9/TW0/TW-3/TW-6/TW-9). If fidelity is given,
    bucket is inferred from the TW_FIDELITY_TO_BUCKET map.
    """
    if bucket is None and fidelity is None:
        raise ValueError("must provide bucket or fidelity")
    if fidelity is not None:
        if fidelity not in TW_FIDELITY_TO_BUCKET:
            raise ValueError(f"unknown fidelity: {fidelity}")
        bucket = TW_FIDELITY_TO_BUCKET[fidelity]
    if bucket not in ("TW_PLUS", "TW_ZERO", "TW_MINUS"):
        raise ValueError(f"unknown bucket: {bucket}")

    recipient_email = recipient_email.strip().lower()
    now = datetime.now(timezone.utc)

    with transaction() as conn:
        # Ensure a row exists (insert-if-missing, update otherwise). SQLite
        # and Postgres both support INSERT ... ON CONFLICT via SQLAlchemy,
        # but the compatibility layer is ugly; doing it as select-then-
        # update-or-insert is clearer.
        existing = conn.execute(
            select(rl_t).where(and_(
                rl_t.c.tenant_id == tenant_id,
                rl_t.c.user_id == user_id,
                rl_t.c.recipient_email == recipient_email,
            ))
        ).first()

        if existing is None:
            conn.execute(rl_t.insert().values(
                tenant_id=tenant_id,
                user_id=user_id,
                recipient_email=recipient_email,
                recipient_name=None,
                tw_bucket=bucket,
                tw_fidelity=fidelity,
                label_source="user",
                confidence=0.85,
                auto_rule=None,
                needs_review=0,
                email_count=0,
                created_at=now,
                updated_at=now,
            ))
        else:
            conn.execute(update(rl_t).where(and_(
                rl_t.c.tenant_id == tenant_id,
                rl_t.c.user_id == user_id,
                rl_t.c.recipient_email == recipient_email,
            )).values(
                tw_bucket=bucket,
                tw_fidelity=fidelity,
                label_source="user",
                confidence=0.85,
                needs_review=0,
                updated_at=now,
            ))

        # Read back the canonical row
        row = conn.execute(
            select(rl_t).where(and_(
                rl_t.c.tenant_id == tenant_id,
                rl_t.c.user_id == user_id,
                rl_t.c.recipient_email == recipient_email,
            ))
        ).first()

    return LabelingQueueItem(
        recipient_email=row.recipient_email,
        recipient_name=row.recipient_name,
        current_bucket=row.tw_bucket,
        current_fidelity=row.tw_fidelity,
        label_source=row.label_source,
        auto_rule=row.auto_rule,
        needs_review=bool(row.needs_review),
        email_count=row.email_count,
    )


def labeling_progress(tenant_id: str, user_id: str) -> dict:
    """Summary stats for the admin dashboard + labeling UI."""
    from db import connection
    from sqlalchemy import func

    with connection() as conn:
        total = conn.execute(
            select(func.count()).select_from(rl_t).where(
                (rl_t.c.tenant_id == tenant_id) & (rl_t.c.user_id == user_id)
            )
        ).scalar() or 0
        user_labeled = conn.execute(
            select(func.count()).select_from(rl_t).where(
                (rl_t.c.tenant_id == tenant_id) &
                (rl_t.c.user_id == user_id) &
                (rl_t.c.label_source == "user")
            )
        ).scalar() or 0
        flagged = conn.execute(
            select(func.count()).select_from(rl_t).where(
                (rl_t.c.tenant_id == tenant_id) &
                (rl_t.c.user_id == user_id) &
                (rl_t.c.needs_review == 1)
            )
        ).scalar() or 0

    return {
        "total_recipients": total,
        "user_labeled": user_labeled,
        "auto_labeled": total - user_labeled,
        "flagged_for_review": flagged,
    }
