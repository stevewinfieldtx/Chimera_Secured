"""
CPP content hashing for change-triggered mirroring.

Every CPP-E has a content hash computed over its meaningful payload:
  - Fitted TW heads (their pickled bytes)
  - Fitted extractor
  - Recipient label map (canonicalized)
  - Training metadata that affects behavior

The hash does NOT include:
  - Training timestamp (changes every enrollment, not a real change)
  - Server-side IDs
  - File paths

Two CPPs that produce identical scoring behavior should have identical
hashes. Two CPPs that would score differently should have different hashes.

Design notes for next-Claude:
  - We hash pickled bytes because that's what we're storing anyway. This
    means the hash changes if sklearn/xgboost internals change between
    library versions. That's OK - a library upgrade is a real change that
    warrants re-mirroring.
  - Keep the hash function stable. If you change what goes into it, all
    tenants' hashes invalidate at once and everyone does a fresh mirror
    push. Bump CPP format version if that happens.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def hash_file(path: Path) -> str:
    """SHA-256 of a file's bytes. Used on pickled artifacts."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_dict(d: dict) -> str:
    """SHA-256 of a dict's canonical JSON. Used for label maps + metadata."""
    canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_cpp_hash(
    head_paths: dict[str, Path],
    extractor_path: Path,
    tw_predictor_path: Path,
    label_map: dict[str, tuple[str, str]],
    meta: dict,
) -> str:
    """
    Compute the content hash for a CPP-E artifact set.

    `head_paths` maps bucket name → Path (only include buckets that have
    trained heads). `label_map` is the predictor's labels dict.

    Returns a hex string suitable for storing in cpps.content_hash.
    """
    parts: dict[str, str] = {}

    # Heads (sorted for determinism)
    for bucket in sorted(head_paths.keys()):
        parts[f"head:{bucket}"] = hash_file(head_paths[bucket])

    # Extractor
    parts["extractor"] = hash_file(extractor_path)

    # TW predictor (may not exist if we're storing labels purely in DB)
    if tw_predictor_path.exists():
        parts["tw_predictor"] = hash_file(tw_predictor_path)

    # Label map: canonicalize so ordering doesn't matter
    parts["labels"] = hash_dict({k: list(v) for k, v in sorted(label_map.items())})

    # Behavioral metadata (training volume affects confidence reporting)
    parts["meta"] = hash_dict({
        "training_email_count": meta.get("training_email_count", 0),
        "coverage": meta.get("tw_coverage", {}),
        "format_version": meta.get("format_version", "1.0"),
    })

    return hash_dict(parts)
