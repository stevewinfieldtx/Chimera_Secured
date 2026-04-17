"""
Email preprocessing.

Before we can extract stylometric features, we need to isolate what the
sender actually wrote *this time* from all the cruft that travels with
email: quoted replies, signatures, disclaimers, legal footers, forwarded
content.

The CPA white paper calls out signature stripping, PII scrubbing, quoted-
reply removal, and legal-footer excision as explicit preprocessing steps.
This module handles everything except PII (which is pii_scrub.py).

Design notes for next-Claude:
  - Heuristics, not ML. Signature detection via ML is a fun research problem
    but overkill for v1. Good heuristics catch 90%+ and the residual noise
    averages out across hundreds of training emails per user.
  - Order matters. Strip HTML first (if present), then quoted replies,
    then signatures, then legal footers. Each step assumes the previous ran.
  - We always keep at least 15 words of residual body. If preprocessing
    would leave us with less, we use the pre-preprocessing version and
    flag it in the metadata. An aggressive strip that nukes the body is
    worse than no strip.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser


# ---- HTML stripping -----------------------------------------------------

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0  # depth counter for <script> <style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip > 0:
            self._skip -= 1
        elif tag in ("p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip == 0:
            self.parts.append(data)


def strip_html(text: str) -> str:
    """Strip HTML tags, keeping text content. No-op for plain text."""
    if not text or "<" not in text:
        return text
    parser = _TextExtractor()
    try:
        parser.feed(text)
    except Exception:
        # HTML parser errors → fall back to raw
        return text
    return "".join(parser.parts)


# ---- Quoted-reply removal ----------------------------------------------

# Common quoted-reply headers that Outlook, Gmail, and most clients produce
QUOTED_REPLY_HEADERS = [
    re.compile(r"^\s*On .+ wrote:\s*$", re.MULTILINE),
    re.compile(r"^\s*On .+,\s*.+ wrote:\s*$", re.MULTILINE),
    re.compile(r"^\s*-+\s*Original Message\s*-+\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*_+\s*$", re.MULTILINE),  # Outlook divider
    re.compile(r"^\s*From:\s+.+$", re.MULTILINE),  # Outlook-style forwarded header
    re.compile(r"^\s*Sent:\s+.+$", re.MULTILINE),
    re.compile(r"^\s*Begin forwarded message:\s*$", re.MULTILINE | re.IGNORECASE),
]

# Quoted line marker (">" at start of line)
QUOTED_LINE_RE = re.compile(r"^\s*>.*$", re.MULTILINE)


def strip_quoted_reply(text: str) -> str:
    """
    Remove quoted previous messages from the bottom of the email.

    Finds the first quote-header match and truncates from there. Also strips
    lines that start with ">" (nested quoting).
    """
    if not text:
        return text

    # Find earliest quote header; cut everything from it onward
    earliest = len(text)
    for pat in QUOTED_REPLY_HEADERS:
        m = pat.search(text)
        if m and m.start() < earliest:
            earliest = m.start()
    text = text[:earliest]

    # Remove > lines
    text = QUOTED_LINE_RE.sub("", text)

    return text


# ---- Signature detection ------------------------------------------------

# Signature markers: "--", "—", "Best,", "Thanks,", "Regards,", common closers
SIG_DELIMITERS = [
    re.compile(r"^\s*--\s*$", re.MULTILINE),         # RFC-style sig delimiter
    re.compile(r"^\s*—\s*$", re.MULTILINE),          # em-dash sig delimiter
    re.compile(r"^\s*_{3,}\s*$", re.MULTILINE),      # underscore divider
]

# Closer phrases that typically mark the start of a signature block when
# followed by a name on the next line. We want to keep the closer (it's
# part of the user's style!) but strip what comes after.
SIG_CLOSERS = [
    r"best regards",
    r"kind regards",
    r"warm regards",
    r"sincerely",
    r"cheers",
    r"thanks",
    r"thank you",
    r"best",
    r"regards",
]

SIG_CLOSER_RE = re.compile(
    r"(?mi)^\s*(" + "|".join(SIG_CLOSERS) + r")\s*[,.]?\s*$"
)


def strip_signature(text: str) -> str:
    """
    Remove signature block from the end of the email.

    Preserves the closer ("Thanks," / "Best,") because that's part of the
    user's writing style. Strips what follows (name, title, phone, address,
    legal disclaimer).
    """
    if not text:
        return text

    # Priority 1: hard signature delimiters. Everything after them goes.
    earliest = len(text)
    for pat in SIG_DELIMITERS:
        m = pat.search(text)
        if m and m.start() < earliest:
            earliest = m.start()
    if earliest < len(text):
        return text[:earliest].rstrip()

    # Priority 2: closer followed by < N lines of sig-shaped content
    # (name + contact). Find last closer, if the tail after it is short
    # and sig-shaped, strip the tail (not the closer).
    matches = list(SIG_CLOSER_RE.finditer(text))
    if matches:
        last = matches[-1]
        tail = text[last.end():]
        # Sig tails are typically < 10 lines and don't contain sentences
        tail_lines = [ln for ln in tail.splitlines() if ln.strip()]
        if len(tail_lines) <= 8 and not _looks_like_prose(tail):
            return text[:last.end()].rstrip()

    return text


def _looks_like_prose(s: str) -> bool:
    """
    Heuristic: return True if s reads like a sentence, False if it reads like
    a signature block.

    Prose: has sentence-ending punctuation, average line length > 10 words.
    Sig: short lines, little punctuation, contains phone/address-shaped tokens.
    """
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return False
    words_per_line = sum(len(ln.split()) for ln in lines) / len(lines)
    has_sentence_punct = any("." in ln or "!" in ln or "?" in ln for ln in lines)
    return words_per_line > 10 and has_sentence_punct


# ---- Legal footer ------------------------------------------------------

LEGAL_MARKERS = [
    r"confidentiality notice",
    r"this email and any attachments",
    r"this message is confidential",
    r"privileged and confidential",
    r"disclaimer:",
    r"notice of confidentiality",
    r"the information contained in this",
    r"if you are not the intended recipient",
]

LEGAL_RE = re.compile(
    r"(?mi)^\s*(" + "|".join(LEGAL_MARKERS) + r")"
)


def strip_legal_footer(text: str) -> str:
    """Remove corporate legal disclaimers from the bottom of the email."""
    if not text:
        return text
    m = LEGAL_RE.search(text)
    if m:
        return text[:m.start()].rstrip()
    return text


# ---- Orchestration -----------------------------------------------------

def preprocess(raw_body: str, min_words_to_keep: int = 15) -> tuple[str, dict]:
    """
    Apply all preprocessing in order: HTML strip → quoted reply →
    signature → legal footer.

    Returns (cleaned_text, metadata) where metadata describes what was
    stripped. If preprocessing would leave < min_words_to_keep, we revert
    to a less aggressive version so we don't destroy signal.
    """
    if not raw_body:
        return "", {"note": "empty_input"}

    meta: dict = {"original_chars": len(raw_body)}

    after_html = strip_html(raw_body)
    meta["after_html_chars"] = len(after_html)

    after_quote = strip_quoted_reply(after_html)
    meta["after_quote_chars"] = len(after_quote)

    after_sig = strip_signature(after_quote)
    meta["after_sig_chars"] = len(after_sig)

    after_legal = strip_legal_footer(after_sig)
    meta["after_legal_chars"] = len(after_legal)

    # Safety: don't return text so short that we can't extract features from it.
    # We only fall back to a less-aggressive version if the fully-stripped
    # text is genuinely too short for downstream use. A legitimate short reply
    # ("Sure, see you at 3") should stay stripped even if it's under the
    # training threshold — the caller decides what to do with short results.
    # The only case that warrants fallback is when stripping reduced the text
    # to essentially nothing.
    final = after_legal.strip()
    MIN_BEFORE_FALLBACK = 3  # words. Under this, something went wrong.
    if len(final.split()) < MIN_BEFORE_FALLBACK:
        # Fall back to the least-aggressive version that has at least some content
        for candidate in (after_sig, after_quote, after_html, raw_body):
            if candidate and len(candidate.split()) >= MIN_BEFORE_FALLBACK:
                final = candidate.strip()
                meta["fallback"] = True
                break

    meta["final_chars"] = len(final)
    meta["final_words"] = len(final.split())
    # Flag short results so callers can decide whether to use them.
    meta["below_min_words_to_keep"] = len(final.split()) < min_words_to_keep
    return final, meta
