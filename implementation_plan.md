# Chimera Secured — Implementation Plan

**Canonical as of:** 2026-04-17
**For:** The next Claude session, and for Steve coming back to this after a few days.
**Supersedes:** the previous version of this file, which had managed-cloud scoring and no TW system. Anything in the other docs in this folder (`architecture_spec.md`, `scoring_redesign.md`, `pilot_readiness_plan.md`, `eval_strategy.md`) that contradicts this plan is stale — this document wins until it is itself superseded.

---

## If you are a fresh Claude session, read this first

You are working with Steve, a solo founder at WinTech Partners. All development on this product — code, docs, schema, deployment configs — happens through Claude sessions. There is no engineering team. When Steve says "we" he means Steve and whichever Claude is in front of him. When he says "you're building this," he means it literally.

Steve has 25 years of channel-sales experience and real partner relationships. He does not have 25 years of engineering patience. The job is to ship, not to architect for a 50-person team that doesn't exist.

**IMPORTANT — filesystem access:** Claude sessions on Steve's setup have direct read/write access to this folder via the `Windows-MCP:FileSystem` tool (and/or `Filesystem:read_multiple_files` for reads). CHECK YOUR TOOLS with `tool_search` at the start of every session. Do NOT write to a sandbox and make Steve copy files manually. Write directly here. The allowed paths are `C:\Users\steve\Documents` and `C:\Users\steve\Downloads`.

### Canonical product and engine names

Don't invent new names. The canonical ones are:

- **WinTech Partners** — the parent platform company (Steve's).
- **NYN Impact** — operating company for business applications, owns Chimera Secured.
- **LifeStages AI** — operating company for faith/creator applications. Not relevant here.
- **CPA** — Communication Personality Analyzer. The engine that produces Communication Personality Profiles. We are building its first version as part of Chimera Secured work; there is no separate CPA team.
- **TDE** — Targeted Decomposition Engine. Already running on Railway. Produces content atoms, not relevant to Chimera Secured v1.
- **TrueGraph** — relationship graph engine. Future. Ignore.
- **Chimera Secured** — NYN Impact's BEC-detection product. This folder is about it.
- **CPP-E** — Communication Personality Profile, email-sourced. What Chimera Secured consumes.
- **CPP-V** — Communication Personality Profile, video-sourced. For YouTube Influencer Analysis. Not relevant here.
- **CPP-P** — Communication Personality Profile, podcast-sourced. Future. Not relevant here.

### What's real, what's aspirational

Steve and past Claude sessions have written polished white papers describing WinTech Partners' three intelligence engines (CPA, TDE, TrueGraph) and two operating companies (NYN Impact, LifeStages AI). The white papers describe all three engines as if they exist. Reality is narrower:

- **TDE** — exists, runs on Railway at `targeteddecomposition-production.up.railway.app`. Chimera Secured doesn't need TDE for v1.
- **CPA** — Step 1 of the build order is DONE and sitting in `cpa/`. Working, tested (20/20 smoke tests pass as of 2026-04-17). Ready for Railway deployment. Next sessions build on it.
- **TrueGraph** — white paper only.
- **Enron collector** — exists, runs on Railway, has ingested the Enron corpus into Postgres. Keep it.
- **Old Shield / TrueWriting stack** (at `...documents\truewriting\`) — reference only. Kimi AI reviewed it and found it structurally flawed. We are rebuilding, not porting.

### What Steve's two pilot partners actually need

**Rain Networks** is one partner, serving downstream channel partners who serve end customers. Pilot size will be 100–2000 seats per downstream partner who opts in, not the full 60,000 seats Rain has access to. There is a second partner Steve has not named in this session.

Both partners need something they can put in front of a real customer and say "this detects BEC, here's how, here's what it catches, here's what it doesn't." They need it in weeks, not months.

### The one thing to remember

Cut first, add later. The white papers describe a large surface area; Chimera Secured v1 needs a small one. Every session that tries to build the whole white paper will fail to ship. Every session that ships a narrow working thing will create the pull for Phase 2.

---

## The v1 product, in one paragraph

Chimera Secured v1 is a service that, for a given inbox owner, can say "does this email look like it was actually written by this person, writing to this specific recipient in their usual way, and does the content make the answer matter?" It answers this by comparing the email to a context-aware fingerprint (CPP-E) built from the user's historical sent items, using three formality levels (formal / average / casual) that capture the fact that people write differently to different recipients, and by checking whether the email's content is asking for something dangerous (wire transfer, credentials, gift cards). Style signal + context signal + content signal, composed so a 5-word lunch email to a friend doesn't trip an alarm but a 5-word wire-transfer email to the same friend does.

---

## Sovereignty architecture: Option A with change-triggered mirroring

This is the central architectural commitment and everything else follows from it.

**Email bodies never leave the customer's tenant.** The CPA enrollment pipeline runs inside the tenant. PII scrubbing, feature extraction, classifier training all happen inside the tenant boundary. The Chimera Secured scorer runs inside the tenant. Incoming emails are scored in-process and discarded. Nothing about day-to-day operation requires Railway connectivity — a tenant with flaky internet or a regulated air-gap still scores their mail.

**The CPP-E mirrors to Railway when — and only when — it changes.** Each CPP-E wraps a content hash of its classifier artifacts plus training metadata. When the incremental-refresh job runs, it recomputes the CPP-E and compares the new hash to the last-mirrored hash. If they match, nothing happens. If they differ, the tenant pushes the new CPP-E to Railway (specifically, to the CPA mirror service, which is the canonical store for CPPs across all WinTech products).

This naturally gives us quarterly-ish mirroring without any timer. Stable writers generate almost no Railway traffic. Writers whose style shifts — new job, new role, personal change — generate a push when the shift materializes. The mirror is always current without being chatty, and the hash history becomes a free audit trail.

**Weekly heartbeat backstop.** Even with change-triggered mirroring, the tenant sends a lightweight "I'm alive, here's my current hash" ping weekly. If the tenant goes dark for 30 days, that's an admin alert. Pennies of traffic, prevents silent mirroring failures.

**Mirroring is opt-in per tenant, default-on.** Tenants that refuse to mirror keep their CPPs entirely local — the product still works for them, they just don't get cross-application CPP sharing when they eventually adopt ClearSignals or Brain Trust Brief. Regulated-vertical tenants can say no to mirroring without saying no to the product.

**What crosses the tenant boundary, explicitly:**
- Fitted classifier artifacts (the three TW heads, see below)
- Feature extraction configuration and feature statistics
- Training metadata (email count, training date, content hash, TW label distribution)
- No email bodies. No raw features that could leak content. No PII.

---

## The TW (TrueWriting) contextual scoring system

This is the architectural soul of the product and the thing that differentiates Chimera Secured from commodity stylometric classifiers.

### The core idea

A single-fingerprint model has to accommodate all the variance in a user's writing inside one distribution. That distribution is wide, because people write differently to their spouse, their CEO, and their accountant. A wide distribution makes impersonation detection weak.

The TW system solves this by modeling writing as a *family* of fingerprints indexed by formality level. A given email is scored against the fingerprint appropriate to its recipient and context, not against the user's overall average. Narrower distributions, sharper detection, fewer false positives.

### Three-bucket model for v1

For v1, we use three TW levels: **TW+** (formal), **TW0** (average), **TW-** (casual). Each user's CPP-E contains three trained classifier heads, one per bucket, trained on the subset of their sent emails labeled for that bucket. Each recipient in the user's address book gets a TW label indicating which bucket their emails should be scored against.

Phase 2 adds nine-level fidelity (TW+3/+6/+9, TW-3/-6/-9). The swipe interface below already captures nine-level data; v1 just collapses it into three buckets at scoring time.

### How recipients get their TW labels

**Step 1 — Auto-classification on enrollment.** When CPA enrolls a user, it walks the user's address book and applies these default rules:

- Recipient's domain is a free consumer provider (gmail, hotmail, yahoo, outlook.com, icloud, aol): default **TW-** (casual). Flagged for review because consumer-domain defaults are the most likely to be wrong (lawyer clients with gmail, bookkeepers with yahoo, etc.). Flagging means "show this recipient at the top of the labeling queue and display a soft advisory in the admin dashboard" — it does not block sending, trigger alerts, or produce user-visible alarms.
- Recipient is in the same M365 tenant directory as the user: default **TW0** (average).
- Recipient is in the same tenant directory AND flagged as executive in the org chart: default **TW+** (formal).
- Recipient is on a known business domain (MX records, has sent enterprise-shaped mail historically): default **TW0**.
- Recipient's email TLD indicates a country the user has written to before in a consistent pattern: default to that user's historical style for that country. Partially handles the cross-cultural case.
- Everything else: default **TW0** with "needs review" flag.

**Step 2 — User swipe labeling.** On enrollment, the user gets access to a labeling interface (web + mobile PWA) showing a queue of recipients sorted by: consumer-domain defaults first (highest correction priority), then by email volume (higher-volume recipients affect more scoring decisions).

The interaction is deliberately simple:

For each recipient card, the user picks a pile:
- Tap "Formal" → enters the formal pile (TW+)
- Tap "Average" → TW0, done
- Tap "Casual" → enters the casual pile (TW-)
- Tap "Skip" → no change, stays on whatever the auto-classification said

If they entered the formal or casual pile, a second screen asks for the fidelity level:
- Swipe right → TW+3 (or TW-3 on the casual screen). "A little more formal."
- Tap → TW+6 (or TW-6). "Moderately more formal."
- Swipe left → TW+9 (or TW-9). "A lot more formal."

No swipe velocity detection — the direction is the only signal. Velocity-based UI is a tuning trap we're deliberately avoiding.

**Step 3 — Continuous refinement.** Whenever the user sends an email to a recipient whose TW label has low confidence, the system can nudge them ("quick question — was this email to Bob more formal than usual, more casual, or about the same?"). Nudging is a v1.1 feature, not v1.0. Ship the enrollment-time labeling first, add nudges later.

### The labeling system is not a gate

Users who never label anything still get the product. Their CPP-E is trained on whatever auto-classification produced, which means TW0 dominates and the system degrades gracefully to something close to single-fingerprint behavior for that user. Labels make the product better; their absence doesn't break it.

### Consumer-domain flagging at scoring time

Related but distinct from labeling: when the scorer evaluates an email to a gmail/hotmail/etc. recipient where the user hasn't labeled that recipient yet, the verdict carries a "recipient flagged for review" note. **This is a soft advisory, not an alarm.** It does not block sending. It does not bells-and-whistles the user. It shows up in the admin dashboard as "these consumer-domain recipients have unreviewed TW labels — ask the user to review." The user corrects once, the label sticks, no more flag.

### Known limitation: cross-cultural communication

The TW axis conflates formality with several adjacent dimensions (vocabulary complexity, directness, sentence structure). Cross-cultural email adjustment — writing more simply to a non-native-English recipient while staying professional — doesn't live purely on the formality axis. The TW system captures it approximately because the per-recipient labels absorb whatever stylistic adjustment the user consistently makes, but the abstraction is leaky.

The country-TLD prior in auto-classification helps with new contacts at foreign domains. Beyond that, v1 accepts the leak. Phase 3 eventually makes CPP-E multi-axis (formality, complexity, directness, structure separately). This is documented here so future-Claude doesn't try to "fix" it in v1 by inventing a new dimension. It's a known limitation and Gate 5 (the pilot pitch) should acknowledge it.

---

## What we are building in v1

### 1. CPA service (tenant-hosted container) — STEP 1, DONE

Status: scaffold complete, 20/20 smoke tests passing. Lives in `cpa/`. See `cpa/README.md` for local-run instructions and endpoint reference. Railway deploy config is in place (`cpa/railway.json`, `cpa/nixpacks.toml`). Ready to deploy against the existing Enron Postgres.

Endpoints implemented:
- `GET /health`
- `POST /enroll` — reads user's sent emails, preprocesses, auto-classifies recipients, trains three TW heads, persists CPP-E
- `POST /score` — loads CPP, picks TW head based on recipient, returns p_authentic + confidence
- `GET /cpp-status` — metadata + mirror state
- `GET /labeling-queue` / `POST /label` / `GET /labeling-progress` — for the labeling UI

**Explicitly out of scope for CPA v1:** Voice Profile Lens, Exemplar Lens, Style Descriptor Lens, Negative-Space Lens as a separate API (can fold into Classifier Lens training later), Counterparty CPPs, CRM integration, automatic retraining cadence.

### 2. Railway-side CPA mirror service — STEP 3, NOT STARTED

A minimal Railway service that receives change-triggered mirrors from tenant CPAs. Two endpoints:
- `POST /mirror` — receives `{tenant_id, user_id, email_sha256, cpp_artifact, hash, heartbeat_only}`
- `GET /cpp/{tenant_id}/{email_sha256}` — for future cross-application consumers

Small (~200 lines). Postgres on Railway, one table for CPPs, one for mirror events.

### 3. Chimera Secured scorer — STEP 4, NOT STARTED

Lives in `chimera_scorer/` (to be created). One endpoint:
- `POST /score` — returns `{verdict, p_fake, p_fake_ci, content_category, tw_level_used, reasons, feedback_id, scorer_version, recipient_review_flag}`

Three detectors:
- **D1 — Stylometric.** Calls local CPA's `/score` for p_authentic.
- **D3 — DLP content category.** Pattern rules + light LLM classification via OpenRouter.
- **D7 — Metadata anomaly.** Send time, sending client, auth source, reply-to match, display-name match.

Composer: calibrated logistic regression over the three detectors, multiplied by a static content-category prior table. Policy layer: hysteresis, threshold, mode gate (shadow/warn/enforce).

**Out of v1 scope:** D2 (LLM-detector), D4 (ask novelty), D5 (recipient style as separate — TW subsumes), D6 (thread coherence).

### 4. Labeling UI (web PWA) — STEP 6, NOT STARTED

Lives in `labeling_ui/` (to be created). Plain list first, swipe overlay later. Both write to CPA's `/label` endpoint.

### 5. M365 Graph mail hook — STEP 7, NOT STARTED

Azure AD app registration + Graph webhook handler. ~300 lines plus deployment guide.

### 6. Enron cross-writer eval — STEP 5, NOT STARTED

Runs on Railway against existing Enron DB. Parallel worker swarm, one per writer. Uses `eval_runs` table already defined in `enron_collector/schema.sql`.

---

## Ship gates

CPA Classifier Lens (when evaluated alone, CPA's published bars):

- AUC > 0.92 overall
- Zero-shot catch > 90% at 2% FPR
- Few-shot catch > 65% at 2% FPR
- High-fidelity catch > 50% at 2% FPR
- Real-world FPR averaging under 3 alerts per user per week
- Human-impersonation catch measured and disclosed

Chimera Secured composite (D1 + D3 + D7 + composer):

- AUC > 0.94 overall
- Zero-shot catch > 92% at 2% FPR
- Few-shot catch > 75% at 2% FPR
- High-fidelity catch > 65% at 2% FPR

Short-email asymmetry (the distinctive product claim):

- Emails under 15 words, scheduling/social category: real-flag rate ≤ 1%
- Emails under 15 words, wire/payment/gift-card category: attacker catch ≥ 80%

TW system:

- TW prediction accuracy ≥ 75% on held-out recipients
- Per-TW-head quality: each of three heads clears AUC > 0.90 on its own bucket

If cross-writer eval shows any of these not holding, D2 (LLM-detector) comes off the Phase 2 list and into v1. Cross-writer eval first, decisions after.

---

## Build order for the code itself

1. **CPA enrollment + scoring + labeling** — **DONE.** Scaffold in `cpa/`, 20/20 tests pass. ~2400 lines of Python.
2. **Railway deployment of CPA against real Enron DB.** Config is ready; just needs Steve to push and attach Postgres. Not done yet.
3. **Railway-side CPA mirror service.** Small sibling service.
4. **Chimera Secured scorer** wrapping CPA as D1 + D3 + D7 + composer + policy layer.
5. **Enron cross-writer eval pipeline.**
6. **Labeling UI.**
7. **M365 Graph mail hook.**
8. **Shadow-mode internal Phase 0 test on Steve's Hotmail.**

---

## What "done" means for v1

- CPA enrollment runs end-to-end on Steve's Hotmail and produces a sensible CPP-E with working auto-classification.
- Swipe/list labeling works and updates TW labels.
- Scorer runs end-to-end in shadow mode.
- CPP-E change-triggered mirroring works.
- Enron cross-writer eval passes the gates above.
- Gate 5 pitch doc exists and Steve can read it to Rain's security lead without hedging.

---

## Things future-Claude should not waste time on

- Do not re-derive Kimi's scoring principles. `scoring_redesign.md` already has them.
- Do not re-design the lens model. V1 builds one lens (Classifier with three TW heads).
- Do not invent new engine or product names. Use the canonical ones.
- Do not sketch the full CPA white paper's implementation. Build the minimum that serves Chimera Secured's pilot.
- Do not rewrite existing documents just because they could be better. Add a header pointing here if they're misaligned.
- Do not treat "cross-cultural communication" as a new dimension to add to v1. Known limitation; multi-axis CPP-E in Phase 3.
- Do not design velocity-based swipe interactions. Fixed direction only.
- Do not propose sending email bodies to the cloud. The sovereignty architecture is the product's differentiator.
- Do not escalate the consumer-domain review flag to an alarm. Soft advisory only.
- Do not write to a sandbox and make Steve copy files. Use Windows-MCP:FileSystem or Filesystem tools to write directly into `C:\Users\steve\Documents\Chimera_Secured\`.

---

## Open questions for Steve

Not blocking v1:

1. Second pilot partner's name.
2. M365 Graph app registration ownership.
3. CPA and Chimera Secured Railway service names / subdomains.
4. Old TrueWriting folder archival — probably archive or ignore.
5. PWA hosting strategy — tenant-deployed or hosted-and-SSO'd.

---

## Quick glossary for new-Claude

- **CPP** — Communication Personality Profile. The fingerprint object.
- **CPP-E / CPP-V / CPP-P** — CPP sourced from email / video / podcast.
- **CPA** — Communication Personality Analyzer. The engine that produces CPPs.
- **TDE** — Targeted Decomposition Engine. Content atoms. Not needed for Chimera Secured v1.
- **TrueGraph** — relationship graph engine. Future.
- **WinTech Partners** — the parent platform company.
- **NYN Impact** — operating company, owns Chimera Secured.
- **First-Party CPP** — a CPP for an internal user. Chimera Secured consumes this.
- **Counterparty CPP** — a CPP for an external contact. For ClearSignals, not Chimera Secured.
- **Classifier Lens** — the CPP lens Chimera Secured consumes.
- **TW** — TrueWriting. The formality-level axis.
- **TW+ / TW0 / TW-** — formal / average / casual buckets for v1.
- **TW+3 / TW+6 / TW+9** — nine-level fidelity captured by swipe UI; v1 scoring collapses to three buckets.
- **Shadow mode** — scorer logs, doesn't act. Phase 0.
- **Warn mode** — scorer adds banner. Phase 2.
- **Enforce mode** — scorer quarantines. Phase 3.
- **Short-email asymmetry** — the distinctive claim. 5-word lunch with weak style match = allow; 5-word wire instruction with weak style match = block.
- **Change-triggered mirroring** — tenant pushes CPP-E to Railway only when its content hash changes. Weekly heartbeat for liveness.

---

## Session log

- **2026-04-16 afternoon/evening.** Initial plan drafted. Architecture + scoring redesign + pilot plan written. Sovereignty architecture debated and landed on Option A + change-triggered mirroring. TW system designed with three buckets and nine-level swipe capture.
- **2026-04-17 early morning.** Step 1 (CPA service) scaffolded: 14 source modules, Pydantic models, FastAPI app, Railway config. ~2400 lines.
- **2026-04-17 morning.** Step 1 tests written and run. Three real bugs caught and fixed: scikit-learn 1.6 + xgboost 2.1 incompatibility (pinned sklearn 1.5.2), preprocessing fallback too aggressive (only reverts if <3 words now), user-lookup mismatch (score_email and /cpp-status now look up by email_sha256 instead of a derived user_id). 20/20 tests pass.
- **2026-04-17 midday.** Steve discovered Claude had been writing to a sandbox, not the local folder. Corrected: files now written directly to `C:\Users\steve\Documents\Chimera_Secured\` via Windows-MCP filesystem tools.

---

## End of plan

If any part of this is wrong or stale, update this document first, then the things that reference it. This is the anchor.
