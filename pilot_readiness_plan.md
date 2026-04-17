# Chimera Secured — Pilot Readiness Plan

**Audience:** Steve (TrueWriting / Chimera Secured founder), as the person who has to honestly decide whether to engage our two pilot partners.

**Bottom line up front:** We are not pilot-ready today. The old lab stack's own ship gate said so (few-shot catch 0.52, high-fidelity catch 0.60, target 0.85), and we are rebuilding fresh rather than porting it forward — so the gate has to be cleared by new code against a proper cross-writer eval. The work is sequenceable. This plan describes the five gates and the phased pilot rollout. The phased rollout is structured so the first customer-facing phase ships in log-only mode, which means we can start getting real-world signal from a pilot partner's environment *before* we've earned full blocking rights.

**The two partners.** Rain Networks is one; the other is separately contracted and will engage on the same phased structure. Rain has up to 60,000 seats available across their downstream partners, but the pilot seat count is determined by which of their partners opt in — treating 60k as the target number would be overselling. A realistic first-pilot size with Rain is likely one or two of their downstream partners, probably in the 100–2,000 seat range per partner.

---

## The five gates

These gates are ordered by dependency. Gate 1 has to pass before Gate 2 is meaningful. Gates 3, 4, and 5 can overlap once Gate 2 is clearing.

### Gate 1 — Single-writer ship gate (Steve's Hotmail)

**Definition.** On held-out real emails from Steve's Hotmail plus the three-tier attacker set (zero-shot, few-shot, high-fidelity), the fresh-build scorer achieves:
- Overall composite AUC ≥ 0.92
- Catch rate at 2% FPR ≥ 0.85 on every tier individually
- Real-email false-flag rate ≤ 3%
- Expected calibration error (ECE) ≤ 0.05
- On short (<15 word) emails: scheduling/social content category FPR ≤ 1% AND wire/payment content category catch ≥ 0.80

**Current state.** The old lab stack hit overall AUC 0.95, zero-shot 0.96, few-shot 0.52, high-fidelity 0.60, real-flag 2.3%. Two tiers failed. We are not attempting to patch the old stack — we are rebuilding, with the LLM-detector head (D2), the content-category prior composer, and the full seven-detector ensemble in from the start. See `scoring_redesign.md` and `architecture_spec.md` for what's being built.

**What has to happen.** Build the fresh scorer per `scoring_redesign.md`. Train the composer on the Enron cross-writer data (see Gate 2 — the two gates share training infrastructure). Run the evaluation against Steve's Hotmail. The short-email asymmetry is a new gate item that the old stack didn't measure, and it is the core product promise — if it's not there, nothing else matters.

**Exit criterion.** A single eval script runs the production scorer container (not a notebook version) against held-out data and emits a JSON report showing all tiers clearing their bars, including the short-email asymmetry.

### Gate 2 — Cross-writer generalization (Enron)

**Definition.** Same metrics as Gate 1, but the scorer is evaluated on 30–50 distinct Enron writers in a leave-one-writer-out fashion. Mean catch@2%FPR across writers ≥ 0.80; worst writer ≥ 0.65; mean ECE ≤ 0.05.

**Why this matters more than anything else.** Right now we have one real identity (Steve). That is the single biggest credibility hole in the pitch to any partner. If the scorer works on Steve because his CPP happened to separate cleanly, we have no way to know that until it fails in someone else's inbox. Enron is the answer. 150+ distinct writers, ~500K emails, publicly released in 2003, legally cleared for research, widely used in NLP literature. It costs nothing and it's the difference between "it works on me" and "it works across genuinely different writing styles."

**What has to happen.** See `eval_strategy.md` for the full plan. Briefly: pick 30–50 Enron writers with ≥200 sent messages; build a CPP for each (using the same CPP builder we're shipping to tenants); generate attacker corpora against each; run the full scorer per writer; aggregate via a parallel agent swarm that targets ~2 hours wall time end-to-end.

**Exit criterion.** Per-writer metrics table plus distribution plots. Mean clears the bar. Worst-case is documented with a hypothesis for why — we need to know which writers the scorer struggles with (short emails? low send volume? highly variable style?) before a partner finds out for us.

### Gate 3 — Adversarial hardening

**Definition.** The attacker-generation pipeline includes at least three distinct adversarial strategies beyond the current three tiers:
1. **Harvested-mailbox RAG attacker** — attacker has retrieval-augmented access to the target's historical sent folder and prompts an LLM with real examples for style grounding. This is the post-account-compromise case.
2. **Multi-LLM ensemble attacker** — generates 5 candidates using 5 different LLMs and picks the candidate closest to the target's style. The attacker is using our own style signal against us.
3. **Human impersonation** — a real person reads 20 of the target's emails and writes a BEC-style ask in their own phrasing, informed by the target's style. The hardest tier; we probably can't fully beat it, but we need to measure the floor.

**Why.** Our current "high-fidelity" tier is still a single LLM given few-shot examples. That's a 2024-era threat. Real attackers in 2026+ will have more. If we can't beat those, we need to know now, not when Rain's partner finds out.

**Exit criterion.** Catch@5%FPR ≥ 0.60 on each of the three adversarial tiers. We loosen the FPR budget here on purpose — these attacks are by construction harder, and we'd rather flag a few more real emails than promise impossible catch on impossible attackers.

### Gate 4 — Operational readiness

**Definition.** The fresh-build deployment can do the following without code changes:

1. **CPP build** — tenant-side builder runs against a real mailbox (M365 Graph path or IMAP), produces a CPP, POSTs to TDE. Incremental nightly refresh works.
2. **TDE CPP API** — accepts CPPs from the email builder, serves them back to the tenant-side scorer with appropriate tenant scoping, handles the multi-source merge case even if video/podcast CPPs aren't present yet (the code path has to work for when they arrive).
3. **Tenant-side scorer** — runs in shadow mode (score + log, no action), warn mode (banner only), or enforce mode (quarantine). Three modes, one container, configured via env.
4. **`/explain` endpoint** — returns the per-detector breakdown described in `architecture_spec.md` for any scored email, so a tenant admin can answer the "why was this flagged?" question.
5. **Feedback ingestion** — tenant admin can mark a scored email as TP/FP/inconclusive; the marker is logged with detector outputs but never the body; opt-in push to Railway-side aggregation works.
6. **Sovereignty verification** — end-to-end smoke test in a real M365 tenant (Steve's, Rain Direct's sandbox) plus a network-trace proving no email body text ever crosses the tenant boundary during scoring.

**Why.** Pilots die not when the model is wrong but when the customer can't understand why the model was wrong, or can't trust the sovereignty claim, or can't give feedback to improve it. Gate 4 is the operational envelope around the detection quality from Gates 1–3.

**Exit criterion.** Gate 4 passes when all six items above are exercised in a live test in a real tenant, with the network trace captured and archived as part of the pilot evidence package.

### Gate 5 — Honest pilot pitch

**Definition.** A three-to-four-page document that can be read aloud to either pilot partner's security lead and that covers:

1. **What Chimera Secured catches and at what confidence.** Grounded in Gates 1–4 numbers, including per-tier catch rates and the short-email asymmetry specifically.
2. **What it does not catch.** Named explicitly: the human-from-compromised-machine attacker writing in perfect style with no payload. We do not detect that. We do not pretend to.
3. **What the first 30 days look like.** Shadow-mode Phase 0, weekly joint review of would-have-been-flagged, joint threshold calibration. The partner sees what the system would do before the system does anything visible.
4. **The sovereign-data story, in plain English.** CPPs leave the tenant; email bodies do not. Here is what is in a CPP (showable sample, no email content); here is the code path that proves bodies never cross; here is where CPPs are stored (TDE on Railway) and who else can use them (only the same tenant, keyed by tenant ID + hashed email).
5. **The CPP sharing story.** TDE is the unified CPP store, and the same CPP can serve other writing-authentication products beyond Chimera Secured. The partner's users, if they later use a video- or podcast-based product from the same platform, will have their email CPP enriched — and the partner should know this is the direction, because it affects the "what's being stored about our users?" conversation.
6. **The stop conditions.** We will pause the pilot if: real-world FPR exceeds 5%, user-reported false positives exceed X/week per 100 users, or we discover an attacker class we cannot detect with a documented frequency above Y.

**Why.** Steve asked for this directly: "We have to have something that we honestly think is going to solve the problem." The pitch is where that honesty gets tested. If the Gate 5 doc can't be written without hedging, we're not ready.

**Exit criterion.** Steve reads it, pushes back on anything that feels oversold, the revision passes his gut check — and then the partner's security lead reads it without needing marketing-speak translation.

---

## Phased pilot rollout

Once the five gates clear, the pilot is staged so early phases gather signal without customer risk.

### Phase 0 — Internal (weeks 0–2, pre-pilot)

Run Chimera Secured against Steve's Hotmail and one sandbox tenant (Rain Direct's or the second partner's) in shadow mode. No user-visible changes. Collect two weeks of real-email scoring data. Compute real-world FPR. Adjust thresholds and content-category priors if needed. Verify `/explain` and feedback paths end-to-end.

**Success signal:** Real-world FPR within 2x of the Enron eval estimate. `/explain` output is readable by a non-engineer (a security lead at a partner tests this, not us).

### Phase 1 — Detection-only at one partner (weeks 3–6)

Roll out to a selected downstream tenant from one of our two pilot partners — ideally one with 100–500 users and a willing admin. Shadow mode, no user-visible changes, but admin sees a weekly dashboard of would-have-been-flagged emails with verdicts and reasons.

**Why start here.** The admin can tell us — for the specific attackers they're actually seeing in their environment — whether our flags look right. We get real-world attacker diversity without risking a single delayed legitimate email. This is the phase where we learn which detectors matter in the wild vs. which were only strong on synthetic attackers.

**Success signal:** Admin-confirmed catch rate ≥ 0.70 on real incidents logged in the window. Would-have-been-flagged real emails that the admin marks "fine" ≤ 3/week per 100 users.

### Phase 2 — Warning banners (weeks 7–10)

Same tenant, same detection, but flagged emails now get an in-client banner: "This email's style is unusual for the sender. Verify before acting on any requests." No blocking, no sender friction. Recipients can mark banners correct or incorrect with one click.

**Why.** This is where we find out whether the warnings are *useful* to humans, not just statistically valid. A banner the recipient ignores is worth nothing. A banner the recipient uses to ask the sender "did you really send this?" is exactly what BEC prevention looks like.

**Success signal:** Banner-useful rate (recipient-marked correct) ≥ 0.60. Banner-annoying rate ≤ 0.15. Admin retention intent ≥ "would renew."

### Phase 3 — Full enforcement (weeks 11–14)

Quarantine verdict = hold at the policy threshold, for flagged security groups first (finance, executives). Sender and admin notified. Recipient sees nothing until release. Other security groups stay on banners.

**Why phased by group.** Finance and executives are both the highest-value targets and the groups most tolerant of a hold-and-review flow.

**Success signal:** Zero confirmed missed BEC incidents on enforcement-enabled groups. Zero confirmed wrongful holds that materially delayed business. Admin-reported net-positive sentiment from the security-group users.

### Phase 4 — Multi-tenant expansion (months 4–6)

Roll out to 5–10 additional tenants across both pilot partners. Start each with the same shadow → warn → enforce phasing, compressed to 2 weeks per phase based on Phase 0–3 learnings. Introduce the distributor/reseller/tenant policy cascade in anger for the first time.

**Success signal:** Per-tenant onboarding time ≤ 4 hours. Per-tenant policy-tuning cycles ≤ 2. Shared false-positive patterns across tenants get codified into default tunings.

### Phase 5 — GA (month 7+)

Chimera Secured is a product, not a pilot. Pricing, packaging, SLAs, incident response, customer success all exist as functions. This plan does not go that far, but it is the target Gate 5 is pointing at.

---

## What this plan explicitly does not promise

1. **A single-signal silver bullet.** Stylometry plateaus. The LLM-detector (D2) is a strong addition but has blind spots (formal human writers read as LLM-like). The right answer is an ensemble of weak detectors composed with content-category priors.
2. **Zero false positives.** A 2% score-rate FPR on a 200-user tenant sending 50 scored emails per user per day is 200 false flags per day. We mitigate with shadow-mode Phase 0, warning banners before blocking, explainability, and per-security-group policy tuning. We do not promise zero.
3. **Defeat of the human-from-your-own-machine attacker.** Said earlier, repeated here because it's the most important thing we are not pretending. If someone sits at your compromised laptop and types a benign ask in your own phrasing with no payload, we do not catch it. We catch it when they start showing the tells: unusual send time, unusual recipient, payload words, LLM-generated phrasing.
4. **One-month pilot readiness.** The gates are sequenceable but honest. Estimate: 8–12 weeks of focused work to clear all five gates with a small team.

---

## The honest self-assessment that motivates this plan

Three things Chimera Secured has going for it that most BEC tools don't: a per-user behavioral fingerprint instead of per-tenant heuristics; a sovereign-data story that is structurally true (the architecture forces it, not a marketing claim); and a content-conditional composer that no commercial tool I've seen implements properly (the short-email asymmetry specifically).

Three things we are weak on: a single-user training set is a credibility gap that no amount of clever math closes — Enron fixes this for free and we should have done it earlier; the old research stack and the old production Shield diverged into separate codebases that we are now abandoning rather than reconciling, which is the right call but means fresh work; the old context layer shipped before it was validated, performed at random, and got quietly disabled — the fix is to gate every new detector through its own ablation before it can enter the composer.

One thing that is genuinely uncertain: whether per-user CPPs transfer well across writers who have very different sending volumes and style consistencies. Enron will tell us. If the answer is "only well for consistent writers," then the product scopes to those users and we are honest about it.
