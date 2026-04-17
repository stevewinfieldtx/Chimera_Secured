"""
PII scrubbing for zero-knowledge content.

The CPA white paper promises that email addresses, phone numbers, and URLs
are replaced with placeholder tokens before feature extraction so the CPP
cannot memorize specific identifiers as shortcuts.

This module does exactly that. Applied BEFORE feature extraction, not after.
Once features are extracted, the original text is discarded.

Design notes for next-Claude:
  - Order matters: URLs first (because they contain @ and dots that the
    email regex would grab), then emails, then phones.
  - Placeholder tokens are chosen to be single tokens that preserve sentence
    structure without introducing features the stylometric model would latch
    onto. __URL__, __EMAIL__, __PHONE__ work well in practice.
  - We deliberately do NOT scrub names. Names are part of writing style
    (how you refer to people) and removing them damages signal. A CPP
    compromise that leaks that "the user mentions 'Bob' a lot" is a weaker
    privacy leak than one that leaks raw email bodies.
  - Currency figures are NOT scrubbed because their presence/magnitude is
    part of the DLP content-category signal downstream. We want "$50,000"
    to still read as "$50,000" when D3 (DLP) scans later.
"""
from __future__ import annotations

import re


# URL pattern: http(s), www, and common TLDs
URL_RE = re.compile(
    r"""
    \b
    (
        (?:https?://|www\.)
        [^\s<>"']+
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Email pattern - intentionally liberal since we're just scrubbing
EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

# Phone patterns - international, US, with/without separators
# Tuned to avoid false-positive on things like "Project 2026-04-17"
PHONE_RE = re.compile(
    r"""
    (?<![\w])
    (?:
        \+\d{1,3}[\s.-]?             # +1 or +44 etc.
        (?:\(?\d{1,4}\)?[\s.-]?){1,4}\d{3,4}
        |
        \(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}    # (555) 123-4567
        |
        \d{3}[\s.-]\d{3}[\s.-]\d{4}          # 555-123-4567
    )
    (?![\w])
    """,
    re.VERBOSE,
)

# Credit-card-shaped numbers. Not perfect but catches obvious leaks.
CC_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

# SSN-shaped
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def scrub(text: str) -> str:
    """Replace PII with placeholder tokens. Input is mutated once and returned."""
    if not text:
        return text
    text = URL_RE.sub("__URL__", text)
    text = EMAIL_RE.sub("__EMAIL__", text)
    text = PHONE_RE.sub("__PHONE__", text)
    text = CC_RE.sub("__CC__", text)
    text = SSN_RE.sub("__SSN__", text)
    return text


def scrub_stats(text: str) -> dict:
    """Count how many of each type were found. Useful for enrollment telemetry."""
    return {
        "url_count": len(URL_RE.findall(text)) if text else 0,
        "email_count": len(EMAIL_RE.findall(text)) if text else 0,
        "phone_count": len(PHONE_RE.findall(text)) if text else 0,
        "cc_count": len(CC_RE.findall(text)) if text else 0,
        "ssn_count": len(SSN_RE.findall(text)) if text else 0,
    }
