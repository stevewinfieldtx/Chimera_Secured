# CPA — Communication Personality Analyzer (v1)

**Canonical as of:** 2026-04-17
**Status:** Scaffold complete. All 20 smoke tests pass. Ready for Railway deployment against the Enron DB, then Step 2–5 of the build order.

This is the first consumer-facing implementation of the CPA engine described in `CPA_White_Paper.md`. For v1, CPA ships only the Classifier Lens (consumed by Chimera Secured) built from email sources. Other lenses (Voice Profile, Style Descriptor, Exemplar, Negative-Space) and the Counterparty CPP class are deferred to Phase 2+.

See `../implementation_plan.md` for the full context, scope, and build order. If anything here contradicts that plan, the plan wins.

## What this service does

Given a user's sent-email history, CPA:

1. Preprocesses each email (strips HTML, quoted replies, signatures, legal footers).
2. Scrubs PII (emails, URLs, phone numbers, credit cards, SSNs) with placeholder tokens.
3. Auto-classifies each recipient into one of three TW buckets (formal / average / casual) using domain heuristics, directory lookup, and country-TLD priors.
4. Trains one calibrated XGBoost classifier per TW bucket against a background corpus sampled from Enron.
5. Persists the fitted heads + TW predictor + feature extractor to disk as a versioned CPP-E artifact, keyed by tenant + SHA-256 of user email.
6. Exposes a scoring API that, given a new email and recipient, picks the right TW head, returns `p_authentic` and a confidence score.

The email bodies never persist — only the fitted features survive. This is the zero-knowledge content model from the CPA white paper.

## Quick start (local)

```bash
cd cpa
pip install -r requirements.txt

# Option A: tiny synthetic background corpus (smoke test only)
python scripts/seed_background.py --fake

# Option B: real corpus from Enron Postgres (requires DATABASE_URL)
DATABASE_URL=postgres://... python scripts/seed_background.py

# Run the tests to verify everything works
python -m pytest tests/ -v

# Start the service
uvicorn src.app:app --host 0.0.0.0 --port 8400 --reload
```

Then hit the endpoints:

```bash
curl http://localhost:8400/health

curl -X POST http://localhost:8400/enroll \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test",
    "user_id": "steve",
    "user_email": "steve@example.com",
    "emails": [
      {"recipient_email": "bob@acme.com", "body": "Hi Bob, quick update..."},
      ...
    ]
  }'

curl -X POST http://localhost:8400/score \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test",
    "user_email": "steve@example.com",
    "recipient_email": "bob@acme.com",
    "email_body": "Hey Bob, is the report ready?"
  }'
```

## Deployment on Railway

```bash
# From the cpa/ directory, push to a new Railway service.
# The nixpacks.toml + railway.json are already configured.

# Required env vars:
DATABASE_URL=postgres://...             # Railway's attached Postgres
CPA_DATA_DIR=/data                      # Persistent volume mount
CPA_ARTIFACTS_DIR=/data/artifacts

# Optional env vars for mirroring to the Railway CPP store (Step 3 of build order):
CPA_MIRROR_URL=https://cpa-mirror.railway.app
CPA_MIRROR_API_KEY=...
```

Run `python scripts/seed_background.py` once after the Enron DB is accessible to build the background corpus. The service will then warm it up on startup.

## Endpoint reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Service liveness, DB health, background corpus size |
| POST | `/enroll` | Build or rebuild a CPP-E for a user |
| POST | `/score` | Score one email against the user's CPP-E |
| GET | `/cpp-status` | CPP metadata, mirror state |
| GET | `/labeling-queue` | Ordered list of recipients needing TW labels |
| POST | `/label` | User writes/overrides a TW label |
| GET | `/labeling-progress` | Summary stats for the admin dashboard |

Full request/response schemas are in `src/models.py`.

## File layout

```
cpa/
├── src/
│   ├── app.py              — FastAPI endpoints
│   ├── config.py           — env-driven config, TW constants, consumer domains
│   ├── db.py               — SQLAlchemy schema + connection helpers
│   ├── models.py           — Pydantic request/response shapes
│   ├── pii_scrub.py        — PII placeholder replacement
│   ├── preprocessing.py    — HTML/quote/signature/legal stripping
│   ├── features.py         — char n-grams + function words + structural
│   ├── auto_classify.py    — recipient → default TW bucket rules
│   ├── classifier.py       — TWHead (one per bucket), TWPredictor
│   ├── background_corpus.py — Enron loader, preprocessed negatives pool
│   ├── enrollment.py       — end-to-end enroll flow
│   ├── scoring.py          — CPP cache + score_email
│   ├── labels.py           — labeling queue + label write-back
│   └── hashing.py          — content hash for change-triggered mirroring
├── tests/
│   └── test_smoke.py       — 20 smoke tests (all passing)
├── scripts/
│   └── seed_background.py  — build the Enron background corpus
├── requirements.txt        — sklearn pinned to 1.5.2 (xgboost 2.1 compat)
├── nixpacks.toml           — Railway build config
└── railway.json            — Railway deploy config
```

## Bugs found and fixed during scaffold QA

The previous session built the scaffold; this session ran the tests. Three real bugs surfaced:

1. **sklearn 1.6 incompatibility with xgboost 2.1.3.** Pinned `scikit-learn==1.5.2`.
2. **Preprocessing fallback too aggressive.** Was reverting to unprocessed text whenever stripping left <15 words, which discarded legitimate short replies. Now only falls back when stripping produces <3 words (genuinely broken). Short-but-clean replies pass through with a `below_min_words_to_keep` flag.
3. **User-lookup mismatch.** `score_email` and `/cpp-status` were deriving a 16-char user_id from the email hash, but enrollment stored whatever user_id the caller passed. Fixed both lookup paths to use `email_sha256` (the stable alias column).

## What's next

In order of build-plan priority:

1. **Step 2** — expose labeling endpoints in a separate module if `labels.py` gets bigger. For v1 it's clean.
2. **Step 3** — Railway-side mirror service. A small sibling service (`../cpa_mirror/`) that accepts `POST /mirror` from tenant-side CPAs on content-hash change.
3. **Step 4** — Chimera Secured scorer wrapping CPA as D1, adding D3 and D7 detectors, the Bayesian composer, and the policy layer.
4. **Step 5** — Enron cross-writer eval pipeline.

Every step has its gate criteria in `../implementation_plan.md` under "Ship gates."

## Known limitations (document honestly, do not paper over)

- **Short-email handling is baseline.** Under 15 words, confidence drops sharply. The Chimera Secured composer handles this via the content-category prior. On its own, CPA's short-email output should not drive decisions.
- **Three TW buckets, not nine.** The labeling UI (Step 6) captures nine-level swipe data, but v1 scoring collapses to three. Phase 2 uses nine-level natively.
- **No counterparty CPPs.** First-Party only.
- **No continuous refresh.** Re-enrollment is manual: POST /enroll again with the fresh email list. Phase 2 adds nightly incremental refresh.
- **FastAPI `on_event` is deprecated.** Cosmetic warning in test output. Migrate to `lifespan` context manager if you're touching `app.py` for other reasons.
- **Synthetic background corpus is tiny.** Use the `--fake` seed for smoke tests only. Run against a real Enron-seeded corpus before trusting any classifier output.
