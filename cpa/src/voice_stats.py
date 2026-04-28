"""
Voice statistics computation.

During enrollment we already have the user's cleaned email corpus. This module
computes aggregate writing-style statistics from those texts and returns a
JSON-serializable dict. The stats are stored alongside the CPP artifacts and
later consumed by voice_profile.py to generate a natural-language writing
style guide the user can export to other LLMs.

Categories computed:
  1. Vocabulary & word choice — complexity, diversity, formality markers
  2. Grammar patterns — voice (active/passive), tense signals, mood
  3. Punctuation habits — rates for every mark, per 1000 words
  4. Sentence structure — length distribution, fragment rate, variety
  5. Rhetorical devices — question frequency, repetition, list usage
  6. Paragraph structure — length, count, density
  7. Tone markers — formality score, pronoun balance, contraction rate
  8. Function word signature — top over/under-used function words
  9. Closer & greeting patterns — how the user opens/closes emails
 10. Idiosyncrasies — capitalization, ellipsis, dash, exclamation habits

Design notes for next-Claude:
  - This runs ONCE during enrollment, not at scoring time.
  - All stats are aggregate (means, std devs, distributions). No raw
    email text is stored — data sovereignty is preserved.
  - The output dict is designed to be human-interpretable so the voice
    profile generator can translate it directly to natural language
    without needing to re-derive anything.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import numpy as np

from features import (
    FIRST_PERSON,
    SECOND_PERSON,
    THIRD_PERSON,
    FUNCTION_WORDS,
    _CONTRACTION_RE,
    _SENT_SPLIT_RE,
    _TOKENIZE_RE,
)


# ---- Helpers ---------------------------------------------------------------

def _safe_mean(vals: list[float]) -> float:
    return float(np.mean(vals)) if vals else 0.0

def _safe_std(vals: list[float]) -> float:
    return float(np.std(vals)) if len(vals) > 1 else 0.0

def _safe_median(vals: list[float]) -> float:
    return float(np.median(vals)) if vals else 0.0

def _percentile(vals: list[float], p: float) -> float:
    return float(np.percentile(vals, p)) if vals else 0.0

def _rate_per_1000(count: int, total: int) -> float:
    return (count / max(total, 1)) * 1000.0


# ---- Passive voice heuristic ----------------------------------------------

_PASSIVE_RE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being)\s+\w+(?:ed|en)\b",
    re.IGNORECASE,
)


# ---- Greeting / closer detection ------------------------------------------

GREETING_PATTERNS = [
    re.compile(r"^\s*(?:hi|hey|hello|dear|good (?:morning|afternoon|evening))\b", re.IGNORECASE),
]

CLOSER_PATTERNS = [
    re.compile(r"(?:best|regards|cheers|thanks|thank you|sincerely|take care|talk soon|warm regards|kind regards)\s*[,.]?\s*$", re.IGNORECASE | re.MULTILINE),
]


# ---- Main computation -----------------------------------------------------

def compute_voice_stats(texts: list[str]) -> dict[str, Any]:
    """
    Compute aggregate writing-style statistics from a list of cleaned email
    bodies. Returns a JSON-serializable dict.
    """
    if not texts:
        return {"error": "no_texts", "email_count": 0}

    n_emails = len(texts)

    # Per-email accumulators
    all_sent_lengths: list[float] = []
    all_word_lengths: list[float] = []
    all_email_word_counts: list[float] = []
    all_para_counts: list[float] = []
    all_words_per_para: list[float] = []

    # Punctuation counters (across all emails)
    total_words = 0
    total_chars = 0
    total_sentences = 0
    punct_counts: dict[str, int] = {
        "comma": 0, "period": 0, "exclamation": 0, "question": 0,
        "semicolon": 0, "colon": 0, "dash": 0, "ellipsis": 0,
        "parenthesis": 0, "quote_double": 0, "quote_single": 0,
    }

    # Pronoun counters
    pronoun_counts = {"first": 0, "second": 0, "third": 0}

    # Function word accumulator
    fw_counts: Counter = Counter()
    total_fw_tokens = 0

    # Contraction counter
    total_contractions = 0

    # Passive voice sentences
    total_passive = 0

    # Sentence variety tracking
    sent_starts: Counter = Counter()  # first word of each sentence
    fragment_count = 0  # sentences with < 4 words

    # Capitalization (mid-sentence caps for emphasis)
    mid_caps_count = 0

    # Greeting/closer tracking
    greeting_count = 0
    closer_count = 0
    greeting_types: Counter = Counter()
    closer_types: Counter = Counter()

    # Short vs long sentence distribution
    short_sents = 0  # < 8 words
    medium_sents = 0  # 8-25 words
    long_sents = 0  # > 25 words

    # All tokens for vocabulary diversity
    all_unique_words: set[str] = set()
    total_token_count = 0

    # --- Process each email ---
    for text in texts:
        if not text or not text.strip():
            continue

        tokens = _TOKENIZE_RE.findall(text)
        lower_tokens = [t.lower() for t in tokens]
        word_count = len(tokens)
        char_count = len(text)

        total_words += word_count
        total_chars += char_count
        all_email_word_counts.append(float(word_count))

        # Vocabulary diversity
        total_token_count += word_count
        all_unique_words.update(lower_tokens)

        # Word lengths
        wl = [len(t) for t in tokens]
        all_word_lengths.extend(wl)

        # Sentences
        sentences = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]
        total_sentences += len(sentences)

        for sent in sentences:
            sent_tokens = _TOKENIZE_RE.findall(sent)
            slen = len(sent_tokens)
            all_sent_lengths.append(float(slen))

            if slen < 4:
                fragment_count += 1
            if slen < 8:
                short_sents += 1
            elif slen > 25:
                long_sents += 1
            else:
                medium_sents += 1

            # First word of sentence
            if sent_tokens:
                sent_starts[sent_tokens[0].lower()] += 1

            # Passive voice check
            if _PASSIVE_RE.search(sent):
                total_passive += 1

        # Paragraphs
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        all_para_counts.append(float(len(paragraphs)))
        for p in paragraphs:
            pw = len(_TOKENIZE_RE.findall(p))
            all_words_per_para.append(float(pw))

        # Punctuation
        punct_counts["comma"] += text.count(",")
        punct_counts["period"] += text.count(".")
        punct_counts["exclamation"] += text.count("!")
        punct_counts["question"] += text.count("?")
        punct_counts["semicolon"] += text.count(";")
        punct_counts["colon"] += text.count(":")
        punct_counts["dash"] += text.count("—") + text.count("–") + text.count(" - ")
        punct_counts["ellipsis"] += text.count("...") + text.count("…")
        punct_counts["parenthesis"] += text.count("(")
        punct_counts["quote_double"] += text.count('"')
        punct_counts["quote_single"] += text.count("'") - len(_CONTRACTION_RE.findall(text))

        # Pronouns
        for t in lower_tokens:
            if t in FIRST_PERSON:
                pronoun_counts["first"] += 1
            elif t in SECOND_PERSON:
                pronoun_counts["second"] += 1
            elif t in THIRD_PERSON:
                pronoun_counts["third"] += 1

        # Function words
        for t in lower_tokens:
            if t in set(FUNCTION_WORDS):
                fw_counts[t] += 1
                total_fw_tokens += 1

        # Contractions
        total_contractions += len(_CONTRACTION_RE.findall(text))

        # Mid-sentence capitalization (ALL CAPS words, excluding first word and "I")
        for i, token in enumerate(tokens):
            if i > 0 and token.isupper() and len(token) > 1 and token != "I":
                mid_caps_count += 1

        # Greetings
        first_line = text.strip().split("\n")[0] if text.strip() else ""
        for gp in GREETING_PATTERNS:
            m = gp.search(first_line)
            if m:
                greeting_count += 1
                greeting_types[m.group(0).strip().lower()] += 1
                break

        # Closers
        for cp in CLOSER_PATTERNS:
            m = cp.search(text)
            if m:
                closer_count += 1
                closer_types[m.group(0).strip().lower().rstrip(",.")] += 1
                break

    # --- Aggregate results ---
    total_sents = max(total_sentences, 1)
    tw = max(total_words, 1)

    # Vocabulary diversity (type-token ratio)
    ttr = len(all_unique_words) / max(total_token_count, 1)

    # Average word complexity (syllable proxy: chars per word)
    avg_word_len = _safe_mean(all_word_lengths)
    long_word_pct = sum(1 for w in all_word_lengths if w > 8) / max(len(all_word_lengths), 1)

    # Function word profile: top 20 most used + bottom 10
    fw_rates = {w: fw_counts.get(w, 0) / max(total_fw_tokens, 1) for w in FUNCTION_WORDS}
    top_fw = sorted(fw_rates.items(), key=lambda x: -x[1])[:20]
    bottom_fw = sorted(fw_rates.items(), key=lambda x: x[1])[:10]

    # Pronoun balance
    total_pronouns = sum(pronoun_counts.values()) or 1
    pronoun_pcts = {k: v / total_pronouns for k, v in pronoun_counts.items()}

    # Sentence start diversity
    top_starts = sent_starts.most_common(15)

    # Punctuation rates per 1000 words
    punct_rates = {k: _rate_per_1000(v, tw) for k, v in punct_counts.items()}

    # Passive voice percentage
    passive_pct = total_passive / total_sents

    stats: dict[str, Any] = {
        "email_count": n_emails,
        "total_words": total_words,
        "total_sentences": total_sentences,

        # 1. Vocabulary
        "vocabulary": {
            "type_token_ratio": round(ttr, 4),
            "unique_words": len(all_unique_words),
            "avg_word_length_chars": round(avg_word_len, 2),
            "long_word_pct": round(long_word_pct, 4),  # words > 8 chars
            "contraction_rate_per_1000": round(_rate_per_1000(total_contractions, tw), 2),
        },

        # 2. Grammar
        "grammar": {
            "passive_voice_pct": round(passive_pct, 4),
            "active_voice_pct": round(1.0 - passive_pct, 4),
            "contraction_rate": round(total_contractions / tw, 4),
            "first_person_rate": round(pronoun_counts["first"] / tw, 4),
            "second_person_rate": round(pronoun_counts["second"] / tw, 4),
            "third_person_rate": round(pronoun_counts["third"] / tw, 4),
            "pronoun_balance": {
                "first_pct": round(pronoun_pcts["first"], 4),
                "second_pct": round(pronoun_pcts["second"], 4),
                "third_pct": round(pronoun_pcts["third"], 4),
            },
        },

        # 3. Punctuation
        "punctuation": punct_rates,

        # 4. Sentence structure
        "sentences": {
            "mean_length": round(_safe_mean(all_sent_lengths), 2),
            "std_length": round(_safe_std(all_sent_lengths), 2),
            "median_length": round(_safe_median(all_sent_lengths), 2),
            "p10_length": round(_percentile(all_sent_lengths, 10), 2),
            "p90_length": round(_percentile(all_sent_lengths, 90), 2),
            "short_pct": round(short_sents / total_sents, 4),  # < 8 words
            "medium_pct": round(medium_sents / total_sents, 4),  # 8-25
            "long_pct": round(long_sents / total_sents, 4),  # > 25
            "fragment_pct": round(fragment_count / total_sents, 4),  # < 4 words
            "top_sentence_starts": [{"word": w, "count": c} for w, c in top_starts],
        },

        # 5. Paragraphs
        "paragraphs": {
            "mean_per_email": round(_safe_mean(all_para_counts), 2),
            "mean_words_per_para": round(_safe_mean(all_words_per_para), 2),
            "std_words_per_para": round(_safe_std(all_words_per_para), 2),
        },

        # 6. Email-level patterns
        "email_patterns": {
            "mean_word_count": round(_safe_mean(all_email_word_counts), 2),
            "std_word_count": round(_safe_std(all_email_word_counts), 2),
            "median_word_count": round(_safe_median(all_email_word_counts), 2),
        },

        # 7. Tone markers
        "tone": {
            "formality_score": _compute_formality_score(
                contraction_rate=total_contractions / tw,
                first_person_rate=pronoun_counts["first"] / tw,
                exclamation_rate=punct_counts["exclamation"] / tw,
                avg_sent_len=_safe_mean(all_sent_lengths),
                passive_pct=passive_pct,
            ),
            "greeting_rate": round(greeting_count / n_emails, 4),
            "closer_rate": round(closer_count / n_emails, 4),
            "top_greetings": greeting_types.most_common(5),
            "top_closers": closer_types.most_common(5),
            "mid_caps_per_1000": round(_rate_per_1000(mid_caps_count, tw), 2),
        },

        # 8. Function word signature
        "function_words": {
            "top_20": [{"word": w, "rate": round(r, 4)} for w, r in top_fw],
            "bottom_10": [{"word": w, "rate": round(r, 4)} for w, r in bottom_fw],
        },
    }

    return stats


def _compute_formality_score(
    contraction_rate: float,
    first_person_rate: float,
    exclamation_rate: float,
    avg_sent_len: float,
    passive_pct: float,
) -> float:
    """
    Composite formality score 0-100. Higher = more formal.

    Informal signals: contractions, first-person, exclamation marks, short sentences.
    Formal signals: passive voice, longer sentences, fewer contractions.
    """
    score = 50.0  # baseline

    # Contractions push informal (-15 max)
    score -= min(contraction_rate * 300, 15)

    # First-person pushes informal (-10 max)
    score -= min(first_person_rate * 200, 10)

    # Exclamation marks push informal (-10 max)
    score -= min(exclamation_rate * 500, 10)

    # Short average sentences push informal (-10 max)
    if avg_sent_len < 12:
        score -= (12 - avg_sent_len)

    # Passive voice pushes formal (+10 max)
    score += min(passive_pct * 40, 10)

    # Long average sentences push formal (+10 max)
    if avg_sent_len > 18:
        score += min((avg_sent_len - 18) * 2, 10)

    return round(max(0, min(100, score)), 1)
