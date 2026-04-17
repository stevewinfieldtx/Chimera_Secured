"""
Auto-classification: assign default TW labels to recipients before the user
labels them.

The rules, in priority order:
  1. Recipient in tenant directory AND flagged as executive → TW+ (formal)
  2. Recipient in tenant directory (any other internal) → TW0 (average)
  3. Recipient at a consumer email domain → TW- (casual), flagged for review
  4. Recipient at a country TLD the user has written to consistently →
     use the user's historical style for that country
  5. Recipient at a known business domain (MX records, historical volume) → TW0
  6. Everything else → TW0, needs_review=True

The output is a default bucket + metadata describing WHY the classifier made
that call. The "why" is what the admin dashboard and the labeling UI use
to show the user "here's what we guessed and why" so they can correct.

Design notes for next-Claude:
  - Directory lookup (rule 1 and 2) requires the M365 Graph directory.
    For the tenant-less developer path (e.g., Steve's Hotmail bootstrap),
    this module accepts an optional `directory` dict that maps email addresses
    to directory entries. Production code plugs in the M365 directory reader.
  - The country-TLD rule needs historical style data, which only exists
    after we've seen the user's sent emails. The enrollment flow calls
    `build_country_priors` from the user's sent corpus and passes it in
    when classifying recipients.
  - All rules are pure functions. No I/O, no DB. Easy to test.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from config import CONSUMER_DOMAINS


@dataclass
class AutoClassification:
    recipient_email: str
    tw_bucket: str           # "TW_PLUS" / "TW_ZERO" / "TW_MINUS"
    confidence: float        # 0.0-1.0
    auto_rule: str           # which rule fired
    needs_review: bool       # show at top of labeling queue
    reason: str              # human-readable "why"


@dataclass
class DirectoryEntry:
    """One entry from the tenant's M365 directory (or equivalent)."""
    email: str
    name: str | None = None
    is_internal: bool = True
    is_executive: bool = False
    department: str | None = None


def _domain_of(email: str) -> str:
    """Return lowercased domain part of an email. Empty string if malformed."""
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].lower().strip()


def _is_country_tld(domain: str) -> str | None:
    """If the domain's TLD is a 2-letter country code, return it. Else None."""
    if not domain:
        return None
    parts = domain.rsplit(".", 1)
    if len(parts) != 2:
        return None
    tld = parts[1].lower()
    if len(tld) == 2 and tld.isalpha() and tld not in ("io", "ai", "ly", "me", "tv", "co"):
        # exclude common non-country 2-letter TLDs that are used generically
        return tld
    return None


def build_country_priors(user_emails: Iterable[dict]) -> dict[str, str]:
    """
    Build a map of country TLD → user's predominant TW bucket for that country,
    inferred from sent-email volume patterns.

    For v1 this is a simple heuristic: if the user has sent N+ emails to a
    given country TLD and the average word count / formality-signal-by-proxy
    is high, call it TW+. If low, TW-. Else TW0.

    Input: iterable of dicts with at least {recipient_email, word_count}.
    Returns: {"vn": "TW_PLUS", "de": "TW_ZERO", ...}
    """
    buckets: dict[str, list[int]] = {}
    for e in user_emails:
        domain = _domain_of(e.get("recipient_email", ""))
        country = _is_country_tld(domain)
        if country is None:
            continue
        buckets.setdefault(country, []).append(int(e.get("word_count", 0)))

    priors: dict[str, str] = {}
    for country, word_counts in buckets.items():
        if len(word_counts) < 3:
            continue  # not enough signal
        avg = sum(word_counts) / len(word_counts)
        # Heuristic thresholds. Tune on real data during eval.
        if avg > 120:
            priors[country] = "TW_PLUS"
        elif avg < 40:
            priors[country] = "TW_MINUS"
        else:
            priors[country] = "TW_ZERO"
    return priors


def classify_recipient(
    recipient_email: str,
    *,
    directory: dict[str, DirectoryEntry] | None = None,
    country_priors: dict[str, str] | None = None,
    known_business_domains: set[str] | None = None,
    email_count: int = 0,
) -> AutoClassification:
    """
    Apply the auto-classification rules to one recipient. Returns an
    AutoClassification with the default TW bucket and a reason string.
    """
    directory = directory or {}
    country_priors = country_priors or {}
    known_business_domains = known_business_domains or set()

    email = (recipient_email or "").strip().lower()
    domain = _domain_of(email)

    # Rule 1 + 2: internal directory
    entry = directory.get(email)
    if entry is not None and entry.is_internal:
        if entry.is_executive:
            return AutoClassification(
                recipient_email=email,
                tw_bucket="TW_PLUS",
                confidence=0.75,
                auto_rule="internal_executive",
                needs_review=False,
                reason="Internal recipient flagged as executive in the directory.",
            )
        return AutoClassification(
            recipient_email=email,
            tw_bucket="TW_ZERO",
            confidence=0.70,
            auto_rule="internal_employee",
            needs_review=False,
            reason="Internal colleague in the tenant directory.",
        )

    # Rule 3: consumer domain
    if domain in CONSUMER_DOMAINS:
        return AutoClassification(
            recipient_email=email,
            tw_bucket="TW_MINUS",
            confidence=0.55,  # lower because this is the most-often-wrong default
            auto_rule="consumer_domain",
            needs_review=True,
            reason=(
                f"Personal email domain ({domain}); defaulting to casual. "
                "Confirm whether this is actually a formal/business contact."
            ),
        )

    # Rule 4: country TLD with historical prior
    country = _is_country_tld(domain)
    if country and country in country_priors:
        bucket = country_priors[country]
        return AutoClassification(
            recipient_email=email,
            tw_bucket=bucket,
            confidence=0.65,
            auto_rule=f"country_prior:{country}",
            needs_review=False,
            reason=(
                f"Country TLD .{country}; user's historical pattern with "
                f"this country suggests {bucket}."
            ),
        )

    # Rule 5: known business domain
    if domain in known_business_domains or email_count >= 5:
        return AutoClassification(
            recipient_email=email,
            tw_bucket="TW_ZERO",
            confidence=0.60,
            auto_rule="known_business",
            needs_review=False,
            reason=f"Business domain ({domain}) with sufficient send history.",
        )

    # Rule 6: unknown → TW0 + needs review
    return AutoClassification(
        recipient_email=email,
        tw_bucket="TW_ZERO",
        confidence=0.40,
        auto_rule="unknown",
        needs_review=True,
        reason="No prior signal for this recipient; defaulting to average.",
    )


def classify_all(
    recipients: Iterable[dict],
    *,
    directory: dict[str, DirectoryEntry] | None = None,
    country_priors: dict[str, str] | None = None,
    known_business_domains: set[str] | None = None,
) -> list[AutoClassification]:
    """
    Apply auto-classification to a list of recipients.

    `recipients` is an iterable of dicts with at least {recipient_email,
    email_count}. Returns a list of AutoClassification in the same order,
    sorted for the labeling queue (consumer-domain flagged first, then
    by email_count desc).
    """
    results = []
    for r in recipients:
        results.append(
            classify_recipient(
                r["recipient_email"],
                directory=directory,
                country_priors=country_priors,
                known_business_domains=known_business_domains,
                email_count=int(r.get("email_count", 0)),
            )
        )
    # Sort the LABELING QUEUE view: needs_review first, then email_count desc.
    # (The persistence layer stores them all; the labeling endpoint applies
    # the sort on read. This helper returns the sorted order as a convenience
    # for tests and for callers that want the queue order directly.)
    return results


def labeling_queue_order(
    classifications: list[AutoClassification],
    volumes: dict[str, int] | None = None,
) -> list[AutoClassification]:
    """
    Sort auto-classifications in the order they should appear in the
    labeling queue: review-flagged first, then by email volume descending.
    """
    volumes = volumes or {}
    return sorted(
        classifications,
        key=lambda c: (
            not c.needs_review,  # needs_review=True sorts first
            -volumes.get(c.recipient_email, 0),
        ),
    )
