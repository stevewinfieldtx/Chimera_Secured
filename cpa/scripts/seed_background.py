#!/usr/bin/env python3
"""
Seed the background corpus from the Enron Postgres DB.

Usage:
    DATABASE_URL=postgresql://... python scripts/seed_background.py

The output goes to the path configured by CPA_BACKGROUND_CORPUS (see
config.py). Safe to re-run; rebuilds the corpus from scratch each time.

When running locally without Postgres, pass --fake to generate a tiny
synthetic corpus just good enough for smoke tests.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running from repo root or from cpa/ directly
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-size", type=int, default=5000,
                    help="How many Enron emails to include (default: 5000)")
    ap.add_argument("--fake", action="store_true",
                    help="Generate a small synthetic corpus (for smoke tests)")
    args = ap.parse_args()

    from background_corpus import BackgroundCorpus, build_from_enron

    if args.fake:
        log.info("building fake corpus for smoke tests")
        # 50 generic email-shaped texts. Just enough to train a classifier.
        synthetic = [
            f"Hi team, following up on the deployment we discussed last week. "
            f"I think we should push the release to Friday so we have time to "
            f"properly test the edge cases. Let me know your thoughts. Thanks, X{i}"
            for i in range(25)
        ] + [
            f"Quick update on the Q{(i%4)+1} numbers. Revenue is tracking about "
            f"{10+i}% above forecast and the pipeline looks strong for next "
            f"quarter. The customer feedback has been positive overall. Best, Y{i}"
            for i in range(25)
        ]
        corpus = BackgroundCorpus()
        corpus.add_raw(synthetic)
        corpus.save()
        log.info("fake corpus saved: %d texts", len(corpus))
        return 0

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        log.error("DATABASE_URL not set. Use --fake for a synthetic corpus.")
        return 1

    corpus = build_from_enron(database_url, sample_size=args.sample_size)
    if len(corpus) == 0:
        log.error("Built empty corpus. Is enron_collector populated?")
        return 1
    corpus.save()
    log.info("corpus saved: %d texts", len(corpus))
    return 0


if __name__ == "__main__":
    sys.exit(main())
