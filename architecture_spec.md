# Chimera Secured — Target Architecture

**Scope of this document.** What Chimera Secured looks like when the pilot-readiness gates clear. This is a fresh-build specification. The old scorer in `...documents\truewriting\` is reference material only — its design was flawed (per the Kimi AI review and the gaps identified in `pilot_readiness_plan.md`), and we are not porting it. The scoring approach is specified in `scoring_redesign.md`; this document covers the deployable architecture around it.

**Three design commitments that override everything else:**

1. **Sovereignty is architectural, not marketing.** Email bodies never leave the customer tenant — not to Anthropic-side infrastructure, not to our services on Railway, not even to a co-located service we control. The CPP — an abstract style fingerprint with no reconstructible content — is the only object that crosses the tenant boundary, and it crosses in one direction only (out of the tenant to TDE, and back into the tenant at scoring time). Every component below either respects this or isn't shipped.
2. **Ensembles, not silver bullets.** No single detector has ever cleared the bar on the few-shot and high-fidelity attacker tiers. The design is an ensemble of seven detectors composed Bayesianly, with the DLP content-category output acting as a prior on the likelihood — so weak style signals on a lunch email and weak style signals on a wire-transfer email produce opposite verdicts by design.
3. **Detection before enforcement.** Every component ships in log-only mode first, earns its way to warn mode, and only gets enforcement rights after sustained real-world calibration. This isn't slow — it's how you avoid the false-positive death spiral that kills every enterprise security tool.

---

## The two halves of the system

Chimera Secured has two deployment surfaces, and the boundary between them is load-bearing. Everything to the left of the boundary runs inside the customer tenant. Everything to the right runs on Railway under our control.

```
┌──────────────────────────────────────┐         ┌──────────────────────────────────────┐
│  TENANT ENVIRONMENT                  │         │  RAILWAY (our infrastructure)        │
│  (customer-controlled)               │         │                                      │
│                                      │         │                                      │
│  ┌────────────────────────────────┐  │  push   │  ┌────────────────────────────────┐  │
│  │ CPP email builder              │──┼─────────┼─▶│ TDE — CPP store & merge engine │  │
│  │ (runs once initially,          │  │  (CPP   │  │ (CPPs keyed by tenant + hash)  │  │
│  │  then incrementally)           │  │  only)  │  │ Accepts: email / video / other │  │
│  └────────────────────────────────┘  │         │  └────────────────────────────────┘  │
│                                      │         │                  │                   │
│  ┌────────────────────────────────┐  │  pull   │                  │                   │
│  │ Tenant-side scorer             │◄─┼─────────┼──────────────────┘                   │
│  │ (D1–D7, composer, policy)      │  │  (CPP   │                                      │
│  │ Email bodies live here and     │  │  only)  │  ┌────────────────────────────────┐  │
│  │ ONLY here                      │  │         │  │ Composer training pipeline     │  │
│  └────────────────────────────────┘  │         │  │ (runs against Enron DB)        │  │
│                                      │         │  │ Produces composer_model.joblib │  │
│  ┌────────────────────────────────┐  │  push   │  └────────────────────────────────┘  │
│  │ Feedback collector (no bodies) │──┼─────────┼─▶┌────────────────────────────────┐  │
│  └────────────────────────────────┘  │         │  │ Feedback aggregation (opt-in)  │  │
│                                      │         │  └────────────────────────────────┘  │
└──────────────────────────────────────┘         └──────────────────────────────────────┘
                                                 
               Email bodies: never cross this line, ever
               CPPs: cross out once at build time, in once per scored email (cached)
               Feedback: crosses out as (detector_outputs, label) tuples — no body
```

---

## Tenant-side components

These run inside the customer's M365 tenant or equivalent — as a containerized service on tenant-owned infrastructure, a serverless function in their cloud account, or an on-prem install for regulated customers. Deployment form varies; the contract does not: **this code sees emails, and the emails never leave this boundary**.

### Component T1 — Tenant-side scorer

The scorer is the engine that decides allow / warn / quarantine. It receives each incoming (or internal) email from the tenant's mail hook, pulls the inbox owner's CPP from TDE (cached locally for up to 24 hours per owner), runs the seven detectors on the email body + CPP, composes the detector outputs into a calibrated `P(fake)`, applies policy, logs, and destroys the body.

The seven detectors are specified in detail later in this document. The composer is specified in `scoring_redesign.md`. Policy is specified below.

**Inputs:** email body, headers, thread history (already in-tenant), inbox owner identity, locally-cached CPP.
**Outputs:** verdict, per-detector scores, `P(fake)` with 95% CI, content category, feedback_id, human-readable reason.
**Side effects:** structured log entry containing the outputs above — but not the body, not even hashed.

**Deployment.** Ships as a Docker container with a small FastAPI surface (`POST /score`). Customer deploys to their M365-connected infrastructure. Tenant's mail hook (M365 Graph webhook, SMTP shim, or mail flow rule) calls `POST /score` for each email. We provide a reference M365 Graph subscription setup as part of the install; customers with different mail infrastructures write their own hook.

**What the scorer container has network access to:**
- TDE on Railway (outbound HTTPS, for CPP pull and feedback push) — allowlistable to specific hostnames
- Nothing else. No outbound LLM API calls, no external feature services, no telemetry to us. If the customer wants to run the LLM-detector (D2) via a cloud API rather than the bundled local model, they configure that themselves with their own keys — but the default build uses only local inference, so the container works fully air-gapped from all external services except TDE.

### Component T2 — CPP email builder (initial run, incremental refresh)

One-time plus incremental: reads the user's historical sent items from their mailbox, produces a CPP artifact, POSTs to TDE. Runs inside the tenant boundary just like the scorer; the only thing that leaves is the CPP itself.

**Initial run:** walks up to N (default 2000) most recent sent emails, extracts features, writes CPP. Takes minutes per user. Triggered by tenant admin for bulk initial provisioning.

**Incremental refresh:** nightly job, processes the day's newly-sent emails, updates the CPP in-place at TDE. Keeps the fingerprint current as the user's style evolves.

**CPP artifact structure** (covered more in `scoring_redesign.md`):
- `universal` block: medium-agnostic features (function-word distributions, character n-grams, sentence-length entropy, vocabulary richness, topic affinity). These are the features that can merge with a video- or podcast-sourced CPP for the same identity.
- `email_only` block: email-specific features (greeting and sign-off patterns, reply conventions, recipient-conditional substyle, thread behavior). These pass through unchanged and don't participate in merging.
- `metadata` block: training volume, temporal coverage, estimated discriminative power from self-consistency tests, CPP format version, source_type="email".

**What the builder sends to TDE:** the CPP artifact, the tenant_id, a tenant-scoped user_id, and a SHA256 of the user's email address (never the plaintext email). TDE stores these and serves them back to the scorer on the next email for that user.

### Component T3 — Feedback collector

When a tenant admin or (per policy) a recipient marks a scored email as true-positive, false-positive, or inconclusive, the collector writes `(feedback_id, detector_outputs, content_category, verdict, admin_label, timestamp)` — no body — to a tenant-local feedback table. On a schedule (default weekly), the collector batches and pushes the feedback to the Railway-side aggregation service, where it feeds quarterly retraining.

Feedback push is opt-in per tenant. Tenants that decline still get their local feedback log; they just don't contribute to global retraining.

---

## Railway-side components

These run on our infrastructure. They handle CPP storage, retraining, and (opt-in) feedback aggregation. **They never see an email body. There is no endpoint, no path, no channel by which a body can reach them.**

### Component R1 — TDE CPP API

TDE (Targeted Decomposition Engine) is the unified CPP store. It is already running on Railway. This project adds the first CPP API to it.

**Endpoints, in spec form:**
```
POST   /cpp
         body: { tenant_id, user_id, email_sha256, source_type,
                 cpp_artifact }
         behavior: stores or updates CPP for this (tenant, user, source).
                   If a CPP already exists for this identity from a
                   different source_type, the stored record keeps them
                   separate — merging happens at GET time.
         auth: tenant API key

GET    /cpp?tenant_id=...&email_sha256=...
         returns: { user_id, merged_cpp, source_types_included,
                    staleness_seconds }
         behavior: looks up all CPPs for this (tenant, email_sha256)
                   across source types, merges them on the universal
                   block (source-weighted by training volume), passes
                   through email_only block if present.
         auth: tenant API key

DELETE /cpp?tenant_id=...&user_id=...
         behavior: removes all CPPs for this user across all sources.
                   GDPR/right-to-erasure path.
         auth: tenant API key

GET    /version
         returns: TDE CPP API version, supported CPP format versions.
```

**Storage shape (Postgres on Railway):**

```
cpps (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    user_id         TEXT NOT NULL,      -- tenant-scoped
    email_sha256    TEXT NOT NULL,      -- for lookup; no plaintext email
    source_type     TEXT NOT NULL,      -- 'email', 'video', 'podcast', ...
    cpp_artifact    JSONB NOT NULL,     -- the CPP itself
    training_volume INT,                -- for merge weighting
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, user_id, source_type)
);
CREATE INDEX ON cpps (tenant_id, email_sha256);
```

There is no `emails` table. There is no `email_body` column anywhere in TDE's schema. The data model makes it impossible to accidentally store email content.

**Identity keying.** Tenant-scoped user_id as the canonical key; email_sha256 as the lookup alias. A user at two tenants = two separate CPPs, no cross-tenant leakage. Decided in `scoring_redesign.md`, confirmed here.

**Merging.** When a user has an email CPP and a video CPP, GET returns a merged artifact: universal blocks combined via source-weighted averaging (weight = `sqrt(training_volume)`, so a 2000-email CPP doesn't completely drown a 30-video CPP), email_only block from the email source passed through. The scorer consumes whatever it gets — if only email is present, it gets an email-only CPP with no merging; if video arrives later, subsequent pulls return a richer merged CPP.

### Component R2 — Composer training pipeline

Runs against the Enron database already on Railway (see `enron_collector/` — that work is done and we keep it). For each selected writer:

1. Build a CPP from 80% of their sent items (using the same builder code as T2, in a training harness).
2. Generate the three-tier attacker corpus plus the adversarial tiers (see `eval_strategy.md`).
3. Run D1–D7 on held-out real + attacker sets.
4. Fit the calibrated logistic regression composer.
5. Measure catch@FPR targets, calibration ECE, per-writer distribution.

Outputs:
- `composer_model.joblib` — the versioned composer artifact, shipped as part of the scorer container.
- `eval_report.html` — the per-release eval report (structure defined in `eval_strategy.md`).
- `model_manifest.json` — version, training data summary, gate-passing numbers, signed hash.

Execution uses the parallel agent swarm described in `eval_strategy.md` — ~2 hours wall time for a full 40-writer cross-validation.

### Component R3 — Feedback aggregation (opt-in)

Receives weekly feedback batches from opt-in tenants. Stores them keyed by anonymized tenant hash. On the quarterly retraining trigger, the aggregate feedback joins the Enron-derived training data for the next composer version.

---

## Layer-0 bypass rules

Not every email should hit the scorer. The following are fast-pathed at the tenant mail hook before `POST /score` is called:

- **Internal-to-internal** — both sender and recipient in the same tenant directory. Risk profile is fundamentally different; we don't score it.
- **Trusted-partner allowlist** — tenant-configured sender domains. (Admins are warned that allowlisted domains are an attacker target in their own right.)
- **System-generated** — Jira, DocuSign, Salesforce, and similar transactional senders, identified by a combination of envelope patterns and sender domain.
- **In-thread replies where the recipient initiated the thread** — the recipient is talking to themselves (or someone they chose to talk to).

Bypassed mail is logged as `verdict=allow, reason=bypass/<rule>` and never reaches the detectors. The eval reporting explicitly separates bypass-rate from scored-rate metrics (see `eval_strategy.md` — reporting "catch rate on all real mail including bypassed" is a dishonest number and we don't publish it).

---

## The seven detectors

Each detector produces `(probability, confidence, reason_string)`. They run inside the tenant boundary as part of the T1 scorer. The composer consumes them.

### D1 — Stylometric distance

**Input:** email body + CPP.
**Features:** character 3/4/5-grams, function-word frequencies, greeting/closing structure, length patterns, negative-space features (what the user *doesn't* do), recipient-conditional style.
**Model:** gradient-boosted classifier over features, wrapped in Platt calibration.
**Known strength:** zero-shot attacker catch is excellent.
**Known weakness:** degrades when the attacker has seen real samples; does not carry the pipeline alone.
**Short-email behavior:** produces a confidence value that drops sharply below 15 words. The composer uses this confidence to downweight D1's contribution on short emails.

### D2 — LLM-generated-text detector

**Input:** email body (CPP not required; this detector is sender-agnostic).
**Features:** token-level perplexity (local small reference model), burstiness (per-sentence perplexity variance — humans vary more than LLMs), token-rank distribution signatures, sentence-length entropy.
**Model:** calibrated logistic regression over the features.
**Why:** an attacker using an LLM produces statistically distinguishable text *regardless* of how cleverly they prompt it for style. D1 asks "does this look like Alice?"; D2 asks "does this look machine-generated at all?" They fail differently. Ensembling captures both.
**Known weakness:** formal human writers (lawyers, HR, senior execs with terse styles) read as LLM-like. D2 alone is low-confidence; the composer handles this via learned interaction terms.

### D3 — DLP content category

**Input:** email body.
**Features:** pattern rules for hard categories (wire, payment_change, credentials, gift_card, sensitive_data, crypto, financial_urgency) and soft categories (urgency framing, secrecy framing). Probabilistic combination over top-2 hard + soft amplification.
**Output:** per-category scores, overall DLP probability, top category label.
**Role in the composer:** the top category label indexes into the content-category prior table. This is the "5-word lunch vs. 5-word wire" asymmetry mechanism.
**Sovereignty note:** D3 runs inside the tenant. The triggering text never leaves with the detector's output — `/explain` reports "DLP flagged: wire / payment instruction, confidence 0.87" and does not echo the email.

### D4 — Ask-type novelty

**Input:** email body + the sender's historical sent items (in-tenant query — a simple semantic index of past sent items, built alongside the CPP).
**Features:** semantic embedding of the email's "ask" (what is this email requesting the recipient do?); nearest-neighbor distance to the sender's prior asks.
**Why:** stylometric match can be perfect and the email still be fake if the *type of request* has never come from this sender before. Account takeover attackers frequently introduce ask types the user has never used — the boss "asking for a wire" for the first time in three years is a novelty signal.
**Storage:** ask embeddings live in-tenant alongside the CPP cache. They never go to TDE.

### D5 — Recipient-conditional style

**Input:** email body + CPP's email_only block + recipient identity.
**Features:** per-recipient style substitutions (the user writes differently to their accountant than to their best friend). Pulled from the CPP.
**Why:** an email from "Alice" to her accountant that reads like her emails to her best friend is a mismatch D1 might miss.

### D6 — Thread coherence

**Input:** email body + prior 2–3 messages in the thread (in-tenant).
**Features:** semantic continuity score between this email and the prior thread. Computed with a local small model; no cloud inference.
**Why:** a thread about scheduling lunch that suddenly contains a wire transfer request has a coherence score near zero. This is the "thread hijack" signal that real BEC attackers produce when they take over a conversation.

### D7 — Metadata anomaly

**Input:** email headers + send metadata + the CPP's metadata profile.
**Features:** send time-of-day deviation, sending client (Outlook web vs. mobile vs. API), geo-IP of the authenticated session, reply-to manipulation, display-name spoofing.
**Why:** the cheapest, highest-precision signals live in the envelope. An email "from Alice" sent at 3am from a Lagos IP on a client she has never used is almost certainly not Alice, regardless of what the body says.

---

## Composer

Specified in full in `scoring_redesign.md`. In brief: learned calibrated logistic regression over the seven detector outputs plus interaction features, multiplied by a content-category prior indexed by D3's top category label, producing `P(fake | signals, content_category)` with a 95% CI.

Replaces all hand-coded thresholds and if-ladders. The composer is ~100 lines of Python plus the fitted model artifact.

---

## Policy layer

Sits between composer output and verdict. Applies, in order:

1. **Override rules** (tenant-configured). "Sender domain on tenant blocklist → force block." Narrow, high-confidence tripwires.
2. **Hysteresis.** If the previous email from this sender in the last 24h was scored `allow`, the threshold for moving to `warn` is 0.5. If it was `warn`, the threshold for moving back to `allow` is 0.4. This 0.1 band suppresses oscillation without hiding a genuine escalation.
3. **Confidence-aware thresholds.** If the 95% CI on `P(fake)` crosses the block threshold, the verdict is downgraded from block to warn. We never quarantine on a measurement we're uncertain about.
4. **Security-group policy.** Tenants can configure different thresholds per security group — stricter for finance and executives, looser for general staff.
5. **Mode gate.** The tenant is running in shadow / warn / enforce mode (pilot phasing per `pilot_readiness_plan.md`). Shadow mode collapses all verdicts to "log only, no user-visible action" regardless of score.

---

## Explainability

Every scored email gets an `/explain` payload:

```
{
  "feedback_id": "...",
  "verdict": "warn",
  "p_fake": 0.63,
  "p_fake_ci_95": [0.51, 0.74],
  "content_category": "wire / payment instruction",
  "content_category_prior": 0.40,
  "detectors": {
    "D1_stylometric":         {"prob": 0.18, "confidence": 0.45, "reason": "..."},
    "D2_llm_detector":        {"prob": 0.71, "confidence": 0.82, "reason": "..."},
    "D3_dlp":                 {"prob": 0.87, "confidence": 0.95, "reason": "wire instruction detected"},
    "D4_ask_novelty":         {"prob": 0.92, "confidence": 0.70, "reason": "no prior ask of this type"},
    "D5_recipient_style":     {"prob": 0.30, "confidence": 0.55, "reason": "..."},
    "D6_thread_coherence":    {"prob": 0.40, "confidence": 0.60, "reason": "..."},
    "D7_metadata":            {"prob": 0.22, "confidence": 0.80, "reason": "..."}
  },
  "hysteresis_applied": false,
  "override_applied": null,
  "cpp_version": "user123/email/v47",
  "scorer_version": "chimera-secured/2026.05.1",
  "composer_version": "bayesian-v1.2"
}
```

The admin UI reads this and renders a human-readable breakdown. Short-email cases are called out specifically: "This is a short email, so style isn't a strong signal — but the content looks like a wire transfer request, which we treat as high risk regardless."

---

## Model artifacts and versioning

Every deployed scorer version produces a signed manifest:

```json
{
  "scorer_version": "chimera-secured/2026.05.1",
  "components": {
    "stylometric_D1":   { "model_sha256": "...", "features": 34 },
    "llm_detector_D2":  { "model_sha256": "...", "reference_model": "gpt2-small-quantized" },
    "dlp_D3":           { "ruleset_sha256": "...", "version": "2.1" },
    "ask_novelty_D4":   { "embedder_sha256": "..." },
    "composer":         { "model_sha256": "...", "version": "bayesian-v1.2",
                          "prior_table_sha256": "..." }
  },
  "trained_at": "2026-04-14T00:00:00Z",
  "eval_metrics": { /* ship-gate numbers from pilot_readiness_plan.md */ },
  "gates_passed": true
}
```

Shield loads this at startup. The `/version` endpoint returns it. Pilots always know exactly which model is in their tenant.

---

## What's deliberately NOT in this spec

1. **No port-in of the old Shield or lab scorer code.** Fresh build. Old code is reference-only.
2. **No email bodies on Railway infrastructure.** Anywhere. No feature, no backdoor, no "for debugging" path.
3. **No per-tenant composer weight training.** Tenants lack labeled BEC attacks; weights are learned globally. Tenants configure thresholds and priors, not coefficients.
4. **No ElevenLabs verbal warning in v1.** Deferred to post-pilot. It's differentiating but only useful after composer calibration is proven stable in production.
5. **No cross-tenant CPP leakage.** Same person in two tenants = two CPPs, keyed by tenant. TDE does not have a "find this person across tenants" API.
6. **No handling of the human-from-compromised-machine attacker.** We say this out loud. A real person sitting at the owner's machine typing a benign-looking request in their own phrasing will not be caught. Chimera Secured is a behavioral security tool, not a possession-proof tool.

---

## Sequencing, restated

Phase 0 (fresh-build foundation):
1. CPP email builder (T2) — local + Railway-deployable
2. TDE CPP API (R1) — Railway
3. Composer training pipeline (R2) — Railway, runs against existing Enron DB
4. Tenant-side scorer (T1) with all seven detectors — deployable container

Phase 1 (pilot readiness):
5. Policy layer (hysteresis, thresholds, overrides)
6. Feedback collector (T3) + aggregation (R3)
7. `/explain` endpoint wiring

Phase 2 (during pilot, once Phase 1 is calibrated):
8. Ask-type novelty (D4) expansion with richer semantic index
9. ElevenLabs verbal warning on HIGH-confidence verdicts
10. Cross-tenant anonymous aggregate statistics (opt-in)

The pilot-readiness gates in `pilot_readiness_plan.md` are the bar for moving between phases.
