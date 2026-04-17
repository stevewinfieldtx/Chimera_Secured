# Chimera Secured — Scoring Redesign

**Scope of this document.** This is the specification for the fresh-build Chimera Secured scorer. It takes Kimi AI's critique of the old `risk_composer.py` as its starting point — every structural criticism Kimi raised is addressed here — and translates those general scoring principles into the specific problem Chimera Secured solves: *does this email match how the inbox owner actually writes, and does the content make the answer matter?*

**What this document replaces.** Nothing. It is a new document. The old scoring code in `...documents\truewriting\` is reference material only; we are not porting it. Kimi's review was of a flawed plan; the plan here is different, and the scorer is built fresh.

**Relationship to Kimi's review.** Kimi analyzed a generic command-line-activity threat scorer. The *principles* it raised transfer cleanly to Chimera Secured: multiplicative over additive composition, calibrated probabilities over arbitrary weights, learned weights over hand-tuned values, hysteresis around thresholds, explicit modeling of score interactions, and configurability over hard-coding. The *specific features* Kimi discussed (command length, entropy, punctuation density, executable score) do not transfer, because Chimera Secured is not analyzing command lines — it is comparing an email's writing style to a per-user Communication Personality Profile and modulating the style signal by what the email is asking the recipient to do.

---

## The one-sentence product statement

Chimera Secured detects Business Email Compromise by comparing each email against a per-user Communication Personality Profile (CPP) that fingerprints how the real inbox owner writes, with the content category of the email acting as a contextual modulator — weak style evidence matters a lot when the email contains a wire instruction, and barely matters at all when the email is asking what's for lunch.

## The sovereignty constraint

**Emails never leave the customer environment.** Not to Chimera Secured's servers, not to a co-located service, not transiently through any pipeline component we control. The scorer runs inside the customer tenant, reads email bodies from in-tenant infrastructure, produces a verdict, and discards the body. The only object that crosses the tenant boundary is the CPP itself, which is an abstract style fingerprint containing no reconstructible email content.

CPPs are stored in the Targeted Decomposition Engine (TDE) on Railway. TDE is pull-only from the tenant's perspective: the tenant-side scorer fetches the current CPP for the inbox owner being evaluated, uses it to score incoming email, and never sends email content back to TDE. TDE is CPP-source-agnostic — it accepts CPPs built from email (this project), from YouTube videos, from podcast transcripts, and from future source types, and it can merge multiple CPPs for the same identity into a unified fingerprint. Our work here is the email-source CPP builder; the TDE API contract has to leave room for the other sources.

---

## What Kimi got right, mapped onto what we're building

### 1. Arbitrary weights must give way to learned weights

**Kimi's point.** Hand-coded coefficients like `0.5*c + 0.5*ctx` or `0.6*c + 0.3*ctx + 0.1*dlp` have no empirical grounding and cannot adapt as attack patterns evolve.

**Our application.** The scorer composes seven detectors (see `architecture_spec.md` for what each detector does). Their combination weights are not hand-written constants. They are learned from the Enron cross-writer evaluation set: for each writer, we have real held-out emails (label = 0) and three tiers of generated attacker emails (label = 1), and we fit a calibrated logistic regression that maps the seven detector outputs to a fake-probability. The weights live in a model artifact (`composer_model.joblib`) that is versioned alongside the scorer. Retraining on expanded data regenerates the artifact; the code does not change.

**What "configurable" means here.** Weights are not a runtime knob. If a tenant wants different behavior, they get different *thresholds* (the verdict cutoffs for allow / warn / block) and different *content-category priors* (see below). The weights themselves are learned globally from eval data and are the same everywhere, because per-tenant weight tuning would require per-tenant labeled attacks, which no tenant has.

### 2. Calibrated probabilities, not rank scores

**Kimi's point.** Threshold-based decisions only mean something if the underlying scores are calibrated probabilities, not arbitrary-scale composites.

**Our application.** The composer's output is `P(fake | signals, content_category)`, a proper probability. We enforce this with two mechanisms:

1. **Platt scaling** on the logistic regression via `CalibratedClassifierCV(method='sigmoid')` during training. This corrects the common overconfidence pattern where the model says 0.9 but the actual rate is 0.7.
2. **Reliability diagram** as a release gate. Before any scorer version ships, its expected calibration error (ECE) must be ≤ 0.05 across 10 probability buckets on the Enron cross-writer holdout. A version that ranks well but is poorly calibrated fails the gate and does not ship.

Downstream policy (allow / warn / quarantine) consumes these probabilities. A tenant saying "warn at 0.5, block at 0.8" means something specific: "warn when the model's calibrated belief that this email is fake is at least 50%."

### 3. Multiplicative composition with content-category modulation

**Kimi's point.** Additive composition (`w₁c + w₂ctx + w₃dlp`) allows high values on one dimension to mask low values on another, which is wrong for security.

**Our application.** This is the heart of the redesign, and it is the place where Kimi's general principle meets the specific BEC insight you articulated. The composer is structured Bayesianly:

```
P(fake | signals, content_category)  ∝  P(signals | fake) · P(fake | content_category)
```

The first factor is the learned logistic-regression likelihood over the seven detector outputs. The second factor is the content-category prior: a lookup keyed on the DLP output's top category label, representing the base rate at which emails of that category turn out to be BEC attempts.

| DLP top category          | P(fake \| category) | Source of prior               |
|---------------------------|---------------------|-------------------------------|
| Wire / payment instruction| 0.40                | FBI IC3 BEC incident reports  |
| Credentials request       | 0.35                | Verizon DBIR phishing stats   |
| Gift card request         | 0.50                | Industry BEC-variant studies  |
| Invoice / payment change  | 0.30                | IC3 + ACH fraud studies       |
| Sensitive data request    | 0.20                | Conservative default          |
| Urgent / secrecy framing  | 0.10                | Framing alone is weak signal  |
| Scheduling / social       | 0.003               | Corpus-estimated base rate    |
| Status / informational    | 0.002               | Corpus-estimated base rate    |
| Unclassified              | 0.01                | Conservative middle ground    |

These priors are tenant-configurable — a law firm might set "sensitive data request" higher than a general business, a payments company might set "wire instruction" higher still. They ship with defaults calibrated from public incident data. The defaults are the starting point; pilot-phase feedback refines them.

**The worked examples that the user gave me, in code:**

- **5-word lunch email, weak style match (likelihood ratio 3x).** Content category = "scheduling/social", prior = 0.003. Posterior ≈ 0.003 × 3 ≈ 0.009. Verdict: allow. We shrug.
- **5-word wire-instruction email, weak style match (likelihood ratio 3x).** Content category = "wire / payment instruction", prior = 0.40. Posterior ≈ 0.40 × 3 ≈ 0.75 (after normalization). Verdict: block. We act.

Same style signal, opposite verdicts, driven by content context. This is what the product promise is.

### 4. Score interactions, not independent features

**Kimi's point.** Treating `chimera`, `context`, and `dlp` as independent additive terms misses correlated patterns like "high DLP + elevated chimera = active exfiltration, not accidental policy violation."

**Our application.** The logistic regression's input is not the seven detector outputs alone. It is the seven outputs *plus* hand-engineered interaction features that capture specific correlated patterns known to indicate BEC:

- `stylometric_dist × dlp_financial` — style mismatch *and* money in the email
- `ask_novelty × thread_coherence_drop` — first-time ask type *and* sudden topic jump in the thread
- `metadata_anomaly × llm_detector_prob` — unusual send context *and* machine-generated text
- `recipient_style_mismatch × ask_novelty` — doesn't write like this to this recipient *and* asking something new

The interactions are added as features before fitting; the logistic regression learns whether each interaction actually contributes beyond the main effects, and its coefficient goes to zero if it doesn't. The ablation study in `eval_strategy.md` reports which interactions are carrying weight and which are noise.

### 5. Hysteresis and confidence intervals around thresholds

**Kimi's point.** Without hysteresis, a score drifting around a threshold oscillates between verdicts, producing alert fatigue. Without confidence intervals, a borderline score (0.70001 vs. 0.99) gets treated the same.

**Our application.**

- **Hysteresis at the policy layer.** A verdict transition from "allow" to "warn" triggers at 0.5. The reverse transition from "warn" back to "allow" on the next email from the same sender triggers only if the score drops below 0.4. This 0.1 band is configurable per tenant. Hysteresis applies across consecutive scored emails from the same sender within a 24-hour window.
- **Confidence intervals on the output.** The scorer returns not just `P(fake)` but a 95% CI computed via bootstrap on the calibration dataset. Borderline emails (CI crosses the threshold) get routed to "warn" rather than "block" regardless of point-estimate, so we never quarantine on a measurement we're uncertain about.
- **Thresholds are tenant-configurable.** The scorer ships with `warn=0.5, block=0.8, block_band=0.1`. Tenants tune these. Rain's downstream partners may want different operating points for different security groups (executives stricter than general staff).

### 6. Rules engine for the parts that belong in rules

**Kimi's point.** ML gives adaptability, rules give interpretability and rapid response to new intelligence. Hybrid is better than either alone.

**Our application.** Two things live in a rules layer, not in the learned model:

1. **Layer 0 bypass rules** — internal-to-internal mail, trusted-partner allowlists, system-generated mail (Jira, DocuSign, Salesforce), replies inside a thread the recipient originated. These should never hit the scorer at all. They are configured as JSON rules per tenant.
2. **Post-scorer override rules** — "if the sender domain is on the tenant's spoofed-domain blocklist, force block regardless of score." These are a narrow set of high-confidence tripwires that run after the scorer and can override its verdict either direction.

The scorer itself is the ML-driven component. The rules are thin bookends around it.

### 7. Feedback loop for continuous improvement

**Kimi's point.** Without admin-labeled feedback, the model cannot improve, and weights drift from reality.

**Our application.** Every scored email gets a `feedback_id`. The tenant admin (or, with per-tenant opt-in, the recipient) can mark a scored email as true-positive, false-positive, or inconclusive. The feedback is logged — *without the email body* — as `(feedback_id, detector_outputs, content_category, verdict, admin_label, timestamp)`. This goes into a tenant-local feedback table and, with admin opt-in, is aggregated anonymously into a cross-tenant retraining corpus.

Retraining runs quarterly in the first year, then on a feedback-volume trigger. Each retrained model goes through the full eval gate (Enron cross-writer + adversarial hardening + calibration) before it ships. Tenants can pin to a specific model version if they don't want automatic updates.

---

## What Kimi didn't know about and we're adding

These are the BEC-specific things the generic scorer review couldn't have caught.

### 1. The style signal is only one of seven detectors, and it's the weakest one alone

Chimera Secured's distinctive capability is the stylometric fingerprint, but it is demonstrably insufficient on its own: the old lab stack hit 0.52 catch on few-shot attackers and 0.60 on high-fidelity attackers when stylometry was the only thing working. The redesign treats stylometric distance as detector D1 of seven, not as the product. The seven detectors (D1 stylometric, D2 LLM-text detector, D3 DLP content category, D4 ask-type novelty, D5 recipient-conditional style, D6 thread coherence, D7 metadata anomaly) are described in detail in `architecture_spec.md`. The composer's job is to combine them. No single one of them is the product.

### 2. Very short emails are a known weak spot, and that's OK

A 5-word email does not give the stylometric detector enough signal to produce a reliable likelihood. The composer handles this explicitly:

- When the email is under a configurable length threshold (default 15 words), D1's confidence is reported as low, and the composer downweights its contribution proportionally.
- The content-category prior does most of the work for short emails. A 5-word lunch ask is fine. A 5-word "wire $50k now" is not, because the prior is high and the other detectors (D2 perplexity, D3 DLP, D4 ask novelty, D6 thread coherence, D7 metadata) still speak even when D1 is silent.
- This is the mathematical encoding of what the user described: "we may not be able to do much from a stylistic view on five words, but it's only a five-word email — if it doesn't contain DLP-protected information, it probably doesn't matter."

### 3. Content awareness without content exposure

The sovereignty constraint means the tenant-side scorer sees the email body, but nothing outside the tenant ever does. The DLP detector (D3) runs inside the tenant, produces category labels and confidence scores, and those categorical outputs — not the triggering text — flow through the rest of the pipeline. The composer's content-category prior lookup happens on the label string ("wire / payment instruction"), not on the email. The `/explain` endpoint reports "DLP flagged: wire / payment instruction, confidence 0.87" and does not echo the matching sentence. This is how we stay contextually aware without exposing content.

### 4. Per-CPP confidence, not just per-email confidence

Not all CPPs are equal. A CPP built from 2,000 sent emails across 2 years is a precise fingerprint; a CPP built from 150 emails over 3 months is a loose sketch. The CPP artifact carries metadata describing its training volume, temporal coverage, and estimated discriminative power (computed at build time via self-consistency tests on the training data). The composer reads this metadata and factors it into D1's confidence. A thin CPP produces lower-confidence style verdicts, which shift more decision weight onto the content-aware detectors (D2, D3, D4).

This also drives the per-tenant FPR reporting split recommended in `eval_strategy.md`: writers with ≥500 training emails are reported separately from writers with 200–500, because we know in advance the latter group will have noisier scores and we'd rather be honest about it than blended average.

### 5. CPP source merging

TDE holds CPPs from multiple source types — email (us), YouTube, podcast, and future sources. When a single identity has multiple CPPs, TDE merges them into a unified fingerprint on request. Our email CPP builder must produce CPPs in a format that admits merging with non-email sources. This means:

- Features that are email-specific (greeting patterns, sign-offs, reply conventions, recipient-conditional style) live in an `email_only` block within the CPP.
- Features that are medium-agnostic (function-word distributions, character n-grams, sentence-length entropy, vocabulary richness, topic affinity) live in a `universal` block.
- At merge time, universal blocks from multiple sources are combined with source-weighted averaging (more training data = more weight), and email-only blocks pass through untouched from the email source.
- The scorer uses the full merged CPP when available; if the inbox owner has only an email CPP (the common case), the scorer uses it as-is.

Most email-pilot users will not have a video CPP. We design for the merging case so the architecture doesn't need rework when someone finally does.

---

## What the scorer looks like, end to end

```
┌──────────────────────────────────────────────────────────────┐
│  TENANT ENVIRONMENT (customer-controlled infrastructure)     │
│                                                              │
│  ┌────────────────────────────────────────────────────┐      │
│  │ 1. Email arrives via M365 Graph / SMTP hook        │      │
│  └──────────────────┬─────────────────────────────────┘      │
│                     ▼                                        │
│  ┌────────────────────────────────────────────────────┐      │
│  │ 2. Layer-0 bypass rules (JSON-configured)          │      │
│  │    → if bypassed: allow, log, done                 │      │
│  └──────────────────┬─────────────────────────────────┘      │
│                     ▼                                        │
│  ┌────────────────────────────────────────────────────┐      │
│  │ 3. Fetch inbox owner's CPP from TDE (pull, cached) │◄──┐  │
│  └──────────────────┬─────────────────────────────────┘   │  │
│                     ▼                                     │  │
│  ┌────────────────────────────────────────────────────┐   │  │
│  │ 4. Run detectors D1–D7 on email body + CPP         │   │  │
│  │    Body never leaves this box                      │   │  │
│  └──────────────────┬─────────────────────────────────┘   │  │
│                     ▼                                     │  │
│  ┌────────────────────────────────────────────────────┐   │  │
│  │ 5. Bayesian composer → calibrated P(fake) + CI     │   │  │
│  └──────────────────┬─────────────────────────────────┘   │  │
│                     ▼                                     │  │
│  ┌────────────────────────────────────────────────────┐   │  │
│  │ 6. Policy layer: hysteresis, thresholds, overrides │   │  │
│  │    → allow / warn / quarantine                     │   │  │
│  └──────────────────┬─────────────────────────────────┘   │  │
│                     ▼                                     │  │
│  ┌────────────────────────────────────────────────────┐   │  │
│  │ 7. Log (no body) + destroy body in memory          │   │  │
│  └────────────────────────────────────────────────────┘   │  │
│                                                           │  │
└───────────────────────────────────────────────────────────┼──┘
                                                            │
        ┌───────────────────────────────────────────────────┘
        │ CPP pull only. Email bodies never cross this line.
        ▼
┌─────────────────────────────────────────────┐
│  TDE on Railway (Targeted Decomp Engine)    │
│                                             │
│  - Stores CPPs keyed by tenant-scoped ID    │
│  - Accepts CPPs from email / video / other  │
│  - Merges multi-source CPPs on read         │
│  - Never sees email bodies                  │
└─────────────────────────────────────────────┘
```

## What we build, in what order

Phases are sequenceable but overlap is expected; the pilot-readiness gates in `pilot_readiness_plan.md` are what we're building toward.

1. **CPP email builder service** (fresh code, Railway-deployable). Reads a user's historical sent items from their mailbox (M365 Graph or IMAP), produces a CPP artifact with the universal + email_only block structure above, POSTs to TDE. Respects the sovereignty constraint: the builder runs in a customer-authorized context, and only the abstract CPP crosses back out.
2. **TDE CPP API** (fresh code, Railway-deployable). Accepts CPPs from builder services, merges same-identity CPPs from different sources, serves CPPs to tenant-side scorers. Identity keying discussed below.
3. **Tenant-side scorer** (fresh code, deployable inside a customer tenant as a container or serverless function). Pulls the CPP from TDE, runs D1–D7 on incoming email, composes, decides, logs. This is the part where "emails never leave the tenant" is architecturally enforced.
4. **Composer training pipeline** (runs on the Enron Railway database). Generates the three-tier attacker corpus per writer, runs detectors on real-vs-attacker, fits the calibrated logistic regression, writes `composer_model.joblib` with a version manifest. The ship gate lives here.
5. **Policy layer** — verdict thresholds, hysteresis, override rules. Simple, configurable, tested.
6. **Feedback ingestion** — accepts admin TP/FP markings, stores detector outputs + label without body, feeds quarterly retraining.

Nothing in this list ports code from `...documents\truewriting\`. Kimi's critique applied to that code; we're not carrying those problems forward.

---

## Identity keying, a decision that has to be made now

The tenant-side scorer has to tell TDE *whose* CPP it wants. There are three options:

1. **Email address as the key.** Simple, but leaks identity across tenants if the same person appears in both.
2. **Tenant-scoped user ID as the key.** Clean, but requires the tenant to maintain a mapping from email addresses to user IDs.
3. **Tenant-scoped user ID, with email as a hashed lookup alias.** The tenant's CPP builder registers a CPP with `(tenant_id, user_id, sha256(email))`. The scorer looks up by `(tenant_id, sha256(email))` and gets back the user_id and CPP. No plaintext email ever lives in TDE. Same person in two tenants = two separate CPPs, no cross-tenant leakage.

**Default: option 3.** Unless the TDE team objects or a pilot partner has a specific requirement, the API is built this way.

---

## Things we are deliberately not doing

1. **Not storing emails in TDE.** Not even encrypted. Not even hashed. The API has no endpoint that accepts email content.
2. **Not per-tenant weight retraining.** Tenants don't have labeled attacks. Weights are learned globally on Enron + public corpora; tenants tune thresholds and priors, not coefficients.
3. **Not shipping a verbal (ElevenLabs) warning in v1.** The old architecture spec had it as a Phase 2+ feature and that still reads right. It's cool, it's differentiating, it's a distraction until the composer calibration is solid in production.
4. **Not trying to catch the human-from-compromised-machine attacker.** A real person sitting at the owner's logged-in laptop typing a benign-looking ask in their own phrasing will not be caught by this system. Stylometry doesn't help (it *is* the owner's machine, their cookies, their client), content-category doesn't help (the ask is benign), metadata doesn't help (nothing is unusual). We say this in Gate 5. Pretending otherwise poisons the pilot.
5. **Not carrying forward the old context layer.** The previous context feature ran at 0.57 AUC and 17% false-flag rate. The new content-category modulation via the DLP detector replaces it, with the mechanism being a learned prior rather than a learned feature. It's a different construct built from scratch.

---

## Success criteria that this redesign must hit

These mirror the pilot-readiness gates and are the bar for "scorer is done enough to pilot."

1. **Calibration.** ECE ≤ 0.05 on Enron cross-writer holdout.
2. **Single-writer tiers.** Catch@2%FPR ≥ 0.85 on each of zero-shot, few-shot, and high-fidelity attackers against Steve's Hotmail CPP.
3. **Cross-writer.** Mean catch@2%FPR ≥ 0.80 across 30–50 Enron writers; worst writer ≥ 0.65.
4. **Adversarial hardening.** Catch@5%FPR ≥ 0.60 on RAG-harvested-mailbox, multi-LLM ensemble, and human-impersonation tiers.
5. **Short-email behavior.** For emails < 15 words with "scheduling/social" content category, real-email false-flag rate ≤ 1%. For the same length with "wire / payment instruction" category, catch rate on attacker corpus ≥ 0.80. This is the asymmetry the product promise depends on; if it's not there, the rest doesn't matter.
6. **Sovereignty verification.** Static analysis pass plus a live network-trace test proving that during end-to-end scoring, no email body text crosses the tenant boundary.

A scorer version that misses any of these does not ship to a pilot. The eval swarm in `eval_strategy.md` exists to produce this report in under two hours of wall time so we can actually iterate.
