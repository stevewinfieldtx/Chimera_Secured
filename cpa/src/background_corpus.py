"""
Background corpus for classifier training.

Each TW head is a discriminative model: it separates the user's writing
(positive class) from "other humans writing email" (negative class). The
negative class is what we call the background corpus.

Quality of the background corpus matters a lot:
  - Too small → classifier overfits to noise in the negative set.
  - Too homogeneous → classifier learns "what's in the background" rather
    than "what's this user's signature."
  - Drawn from too-different a distribution → classifier separates based on
    irrelevant features (topic, era, genre).

The CPA white paper specifies "a combination of real human email (Enron
corpus and contemporary supplements) and diverse synthetic human
communication (multi-LLM, multi-persona, multi-temperature generation)."

For v1 we start with Enron-only. It's 500K real emails from 150 real
writers, freely available, and already sitting in our Railway Postgres
via the enron_collector service. The LLM-generated diverse supplement is
Phase 2 work — it will help few-shot and high-fidelity catch rates when
we add D2 (the LLM-detector head). Ship v1 with Enron, upgrade later.

Design notes for next-Claude:
  - The background corpus is a pool, not a fixed set. Each TW head's
    training call samples BACKGROUND_SAMPLE_SIZE texts from the pool at
    fit time. Different heads, different samples - that's fine.
  - We keep the pool in memory as a list of strings, persisted to disk
    as a pickled list. Not huge - Enron per-email average is ~800 chars,
    so 5000 emails is ~4MB. Easy.
  - We run the same preprocessing pipeline (HTML strip, quote strip,
    signature strip, PII scrub) on background texts that we run on
    positives. Otherwise the classifier learns "user writes with signature,
    background doesn't" which is meaningless.
"""
from __future__ import annotations

import logging
import os
import pickle
import random
from pathlib import Path

from config import BACKGROUND_CORPUS_PATH, BACKGROUND_SAMPLE_SIZE
from pii_scrub import scrub
from preprocessing import preprocess

log = logging.getLogger(__name__)


class BackgroundCorpus:
    """
    A pool of preprocessed, PII-scrubbed text drawn from real-human email.
    Used as the negative class during TW head training.
    """

    def __init__(self, texts: list[str] | None = None):
        self.texts: list[str] = texts or []

    def __len__(self) -> int:
        return len(self.texts)

    def sample(self, n: int, rng: random.Random | None = None) -> list[str]:
        """Random sample of n texts. Returns fewer if pool is smaller than n."""
        rng = rng or random.Random(42)
        if n >= len(self.texts):
            return list(self.texts)
        return rng.sample(self.texts, n)

    def add_raw(self, raw_texts: list[str]) -> None:
        """Preprocess and add a batch of raw texts."""
        added = 0
        for raw in raw_texts:
            cleaned, _meta = preprocess(raw)
            scrubbed = scrub(cleaned)
            if scrubbed and len(scrubbed.split()) >= 15:
                self.texts.append(scrubbed)
                added += 1
        log.info("BackgroundCorpus.add_raw: added=%d skipped=%d", added, len(raw_texts) - added)

    # ---- Persistence ----------------------------------------------------

    def save(self, path: Path = BACKGROUND_CORPUS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"texts": self.texts, "version": 1}, f)
        log.info("BackgroundCorpus saved: path=%s count=%d", path, len(self.texts))

    @classmethod
    def load(cls, path: Path = BACKGROUND_CORPUS_PATH) -> "BackgroundCorpus":
        if not path.exists():
            log.warning("BackgroundCorpus.load: no file at %s; returning empty corpus", path)
            return cls()
        with path.open("rb") as f:
            data = pickle.load(f)
        return cls(texts=data["texts"])


# ---- Enron loader --------------------------------------------------------

def build_from_enron(
    database_url: str,
    sample_size: int = 5000,
    exclude_writer: str | None = None,
    random_seed: int = 42,
) -> BackgroundCorpus:
    """
    Pull a sample of body_text from the Enron Postgres DB.

    The `exclude_writer` parameter lets the cross-writer eval exclude the
    writer being evaluated, so we never train a user's classifier against
    background drawn from that user. Leaving it as None uses the full pool.

    This requires the Enron DB to be populated by enron_collector/. If
    DATABASE_URL isn't reachable or `emails` doesn't exist, returns empty.
    """
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        log.error("sqlalchemy not available; cannot build from Enron")
        return BackgroundCorpus()

    engine = create_engine(database_url, future=True)
    rng = random.Random(random_seed)

    # Tablesample + filter. We want balanced writer coverage, not a volume-
    # dominated draw, so we cap per-writer contribution.
    PER_WRITER_CAP = 30

    query = """
        SELECT mailbox_owner, body_text
        FROM emails
        WHERE body_text IS NOT NULL
          AND word_count >= 15
          AND word_count <= 400
    """
    params: dict = {}
    if exclude_writer:
        query += " AND mailbox_owner != :excl"
        params["excl"] = exclude_writer

    query += " ORDER BY random() LIMIT :limit"
    params["limit"] = sample_size * 3  # oversample; we'll filter and cap

    log.info("build_from_enron: querying (sample_size=%d exclude=%s)", sample_size, exclude_writer)

    try:
        with engine.connect() as conn:
            rows = list(conn.execute(text(query), params))
    except Exception as e:
        log.error("build_from_enron: DB query failed: %s", e)
        return BackgroundCorpus()

    per_writer: dict[str, int] = {}
    raw_texts: list[str] = []
    for owner, body in rows:
        if per_writer.get(owner, 0) >= PER_WRITER_CAP:
            continue
        raw_texts.append(body)
        per_writer[owner] = per_writer.get(owner, 0) + 1
        if len(raw_texts) >= sample_size:
            break

    corpus = BackgroundCorpus()
    corpus.add_raw(raw_texts)
    log.info(
        "build_from_enron: writers=%d raw_count=%d final_count=%d",
        len(per_writer), len(raw_texts), len(corpus),
    )
    return corpus


# ---- Helpers -------------------------------------------------------------

def ensure_background_corpus() -> BackgroundCorpus:
    """
    Load the persisted background corpus, or build it from Enron if missing.
    Returns the corpus. Safe to call at startup.
    """
    corpus = BackgroundCorpus.load()
    if len(corpus) >= BACKGROUND_SAMPLE_SIZE:
        return corpus

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url or "postgres" not in database_url:
        log.warning(
            "ensure_background_corpus: no Postgres DATABASE_URL; "
            "corpus will be empty until manually seeded"
        )
        return corpus

    corpus = build_from_enron(database_url, sample_size=5000)
    if len(corpus) > 0:
        corpus.save()
    return corpus
