# Chimera Secured — Evaluation Strategy

**The single biggest credibility gap in Chimera Secured today is that it has been trained, tuned, and evaluated on exactly one real human.** Every number in every internal report traces back to Steve's Hotmail. That's not a fatal problem — it's a solvable one — but it *is* the first thing a serious security buyer will ask about, and if we walk into one of our two pilot partners without a real answer, the pilot dies in the first call.

This document is the plan for how we honestly earn the right to say "this works."

**Framing note:** This eval plan evaluates the fresh-build scorer specified in `scoring_redesign.md` and `architecture_spec.md`. The old lab stack in `...documents\truewriting\` is not what's being measured here. Any historical numbers from the old stack are noted for context only — they are the problem we're trying to improve on, not the baseline we're claiming.

---

## The three-part eval stack

The eval has to answer three different questions. Each one needs its own data, its own method, and its own bar. Smashing them together is what led the old lab numbers to look better than they were.

### Part 1 — Does it work on Steve? (single-writer, in-distribution)

Answers: can we detect impersonations of a specific, well-profiled writer whose sending history we've seen?

**Data:** Steve's Hotmail sent items (CPP training + held-out real emails) + three-tier attacker corpus (zero-shot, few-shot, high-fidelity LLM impersonation).

**Bar:** Overall AUC ≥ 0.92, catch@2%FPR ≥ 0.85 per tier, real-false-flag ≤ 3%, ECE ≤ 0.05, short-email asymmetry as specified below.

**Status:** This part of the eval cannot run yet because the fresh-build scorer is in-progress. It will run as Gate 1 of `pilot_readiness_plan.md`.

**The short-email asymmetry criterion (new, specific to the product promise):**

For emails under 15 words, we measure catch and FPR separately by DLP content category:

| Short-email condition                                | Bar            |
|------------------------------------------------------|----------------|
| Scheduling/social category, real emails              | FPR ≤ 1%       |
| Scheduling/social category, attacker emails          | catch ≥ 0.20 (genuinely hard; we don't promise much here) |
| Wire/payment/gift-card category, real emails         | FPR ≤ 5% (yes, higher — this is the tenant's high-value security zone, and short-but-financial real emails are rare) |
| Wire/payment/gift-card category, attacker emails     | catch ≥ 0.80   |

This is where the content-conditional composer's claim becomes an evaluable number. If the composer produces the right asymmetry, this table passes. If it produces a uniform response across categories, the headline AUC can be fine and the product still doesn't do what we say it does. This criterion is non-negotiable — it's the difference between "yet another stylometric BEC tool" and "contextually aware BEC tool."

### Part 2 — Does it generalize? (cross-writer, Enron corpus)

This is the gap the old lab evals did not close, and it is the gap pilot partners will ask about first. The question: if we pick a writer neither we nor the scorer has ever seen, build a CPP from their sent items, and run the same attacker pipeline, does the detector still work?

**Data:** The Enron email dataset, already loaded into Railway Postgres by `enron_collector/`. ~500,000 emails from ~150 real employees, publicly released in 2003 as part of FERC's investigation, legally cleared for research use, widely used in NLP literature.

**Method — per-writer leave-one-out eval:**

1. **Writer selection.** Pick 30–50 Enron writers with ≥200 sent emails. Diversity across role (exec / legal / trader / operations), volume (200-count to 500-count), and consistency (low and high `stddev_words` per the `writer_stats` view).

2. **CPP build per writer.** For each selected writer, run the same CPP builder we're shipping to tenants on 80% of their sent items. This is important — we evaluate the real builder, not a separate training script. The builder writes the CPP to TDE exactly the way it would in production, and the scorer pulls it back the same way.

3. **Attacker generation per writer.** Reuse the tiered generation pipeline to produce the three-tier attacker corpus plus the three adversarial tiers: 200 zero-shot, 200 few-shot, 200 high-fidelity, 100 RAG-harvested-mailbox, 100 multi-LLM ensemble, and 20–50 human-impersonation (the last tier is partly manual — we farm out to human collaborators offline and load the corpus). That's ~670–1000 attackers per writer × 40 writers ≈ 27,000–40,000 generated emails. At current LLM costs, $50–200 end-to-end.

4. **Per-writer eval.** Run the full fresh-build scorer (pulling CPP from TDE just like production) against each writer's held-out real + all attacker tiers. Record AUC, catch@FPR targets per tier, real-false-flag rate, ECE, short-email asymmetry.

5. **Aggregate.** Mean ± std across writers. Worst-case writer. Distribution plots by writer-volume, writer-consistency, training-email-count.

**Bar:** Mean catch@2%FPR ≥ 0.80 across writers. Worst writer ≥ 0.65. Real-false-flag ≤ 3% for writers with ≥500 training emails, ≤5% for writers with 200–500. Mean ECE ≤ 0.05. Short-email asymmetry criterion from Part 1 holds at the cross-writer mean.

**What we learn that we cannot learn any other way:**
- Which writer profiles the fresh-build scorer works well on, and which it struggles with
- Whether the content-conditional composer's short-email behavior holds across writers or is a Steve-specific quirk
- Whether the features pick up per-writer fingerprints or just generic English statistics
- What the real-world FPR distribution looks like across a population, not just one user
- Whether the LLM-detector (D2) helps or hurts when a writer happens to write in a naturally LLM-like formal register

### Part 3 — Does it survive an attacker who's trying? (adversarial hardening)

Current three tiers assume the attacker has a few real examples and an LLM. By the time we're in production, real attackers will have more. This part of the eval asks: what's the scorer's behavior against attacker classes we haven't defended against yet?

**Adversarial tiers:**

1. **Harvested-mailbox RAG attacker.** Attacker has retrieval-augmented access to the target's historical sent folder. Prompt: "Write an email from [target] to [recipient] about [topic]. Here are 50 of their real emails for style reference; use them verbatim where natural." Simulates the post-compromise case.

2. **Multi-LLM ensemble attacker.** Generate 5 candidates per attack using 5 different LLMs (Claude, GPT-4, Llama, Mistral, Gemini). Pick the candidate whose stylometric distance to the target is lowest. The attacker is using our own style signal against us.

3. **Human impersonation.** A real person reads 20 of the target's emails and writes a BEC-style ask in their own phrasing, informed by the target's style. Hardest tier; we probably can't fully beat it. Need at least 20–50 per writer from willing human collaborators. This tier is the honest floor.

4. **Signature/PII-preserving attacker.** Attacker includes the target's real signature block, real phone number, real office address harvested from reply chains. This was the bug that inflated an early iteration of the old lab stack's scores; we test for it, not get surprised by it.

**Bar:** Catch@5%FPR ≥ 0.60 per adversarial tier. FPR budget loosens intentionally — these attackers are genuinely harder, and we'd rather flag a few extra real emails than promise impossible catch.

---

## Parallel execution with an agent swarm

**The historical problem.** Each writer eval — generate 600+ attacker emails, score 750+ emails through the composite, compute metrics — takes 30–60 minutes of wall time single-threaded. Running 40 writers sequentially is 20–40 hours. Past eval cycles turned into multi-day waits that discouraged experimentation. Not OK for iteration velocity.

**The solution.** Parallel agent execution:

### Swarm topology

- **Orchestrator agent** (1): reads the writer manifest from Railway Postgres, dispatches writer-eval jobs to workers, aggregates results, generates the final report.
- **Attacker generation workers** (5–10): each takes one writer, runs the three-tier + adversarial-tier generation, writes attacker corpus to the Railway DB. Embarrassingly parallel. Rate-limited by OpenRouter API budget, not CPU.
- **Scoring workers** (5–10): each takes one writer's attacker corpus + real held-out + CPP (pulled from TDE), runs the full fresh-build scorer, writes per-writer metrics JSON. Parallel by writer.
- **Adversarial workers** (2–4): specialized workers for the four adversarial tiers. Human-impersonation isn't automatable — the corpus is pre-loaded from offline human work.
- **Aggregation agent** (1): reads all per-writer metrics, computes distribution stats, generates plots, writes the final report to `eval_results/cross_writer_YYYYMMDD.html` + JSON.

### Practical notes

- Workers run as independent Python processes (not threads — GIL matters for feature extraction) and coordinate via the Railway Postgres `eval_runs` table already defined in `enron_collector/schema.sql`. No Redis/Celery; this is tens of jobs.
- OpenRouter rate limits bind attacker generation. 10 parallel workers hit ~60 req/s, within most OpenRouter plan limits, but watch the dashboard.
- Each worker writes its own log. A failing writer doesn't poison the run. The orchestrator retries failed writers at the end.
- Expected wall time with 8 workers on Railway: ~2 hours for full 40-writer cross-validation. That's the difference between "run this overnight once a week" and "run this every time I try a new feature."

### Gating step: dry-run on 3 writers before the full swarm

Every eval run starts with 3 random writers first. If metrics look sensible (not all writers scoring 0.99 — that means a leak; not all scoring 0.5 — that means the scorer isn't learning), the full swarm kicks off. If the dry-run looks weird, we debug with a fast feedback loop instead of discovering the problem 2 hours later.

---

## Ablation studies — what actually matters

Once the scorer has seven detectors plus the Bayesian composer, every shipped version must answer: what does each component contribute? Complexity has a maintenance cost, and a simple model that performs within margin-of-error of a complex one wins every time.

**Ablation matrix (run per release candidate):**

|                                    | Overall AUC | Few-shot catch | High-fid catch | Short-wire catch | Short-lunch FPR | Real FPR |
|------------------------------------|-------------|----------------|----------------|------------------|-----------------|----------|
| D1 (stylometric) only              | ?           | ?              | ?              | ?                | ?               | ?        |
| D2 (LLM-detector) only             | ?           | ?              | ?              | ?                | ?               | ?        |
| D3 (DLP) only                      | ?           | ?              | ?              | ?                | ?               | ?        |
| D1 + D2                            | ?           | ?              | ?              | ?                | ?               | ?        |
| D1 + D3                            | ?           | ?              | ?              | ?                | ?               | ?        |
| D1 + D2 + D3 (core)                | ?           | ?              | ?              | ?                | ?               | ?        |
| Core + D4 (ask novelty)            | ?           | ?              | ?              | ?                | ?               | ?        |
| Core + D6 (thread coherence)       | ?           | ?              | ?              | ?                | ?               | ?        |
| Full (D1–D7) + composer            | ?           | ?              | ?              | ?                | ?               | ?        |

The short-email columns are added specifically because they measure the content-conditional composer's value. If "D1 + D3 only" hits the short-email asymmetry as well as the full seven-detector ensemble, we should seriously consider shipping D1 + D3 + composer and deferring D4/D5/D6/D7 until we need them.

**Interaction-feature ablation (composer-level):**

| Interaction feature                                | Coefficient | Removed-ΔAUC | Keep? |
|----------------------------------------------------|-------------|--------------|-------|
| stylometric_dist × dlp_financial                   | ?           | ?            | ?     |
| ask_novelty × thread_coherence_drop                | ?           | ?            | ?     |
| metadata_anomaly × llm_detector_prob               | ?           | ?            | ?     |
| recipient_style_mismatch × ask_novelty             | ?           | ?            | ?     |

If any interaction's removed-ΔAUC is within 0.005 of the full composer, we drop it. Fewer moving parts.

---

## Calibration reliability

The scorer emits probabilities, not ranks — because pilot phases use threshold policy (warn at 0.5, block at 0.8) and those thresholds only mean something if the probabilities are calibrated.

**Reliability diagram check (per release):**
- Bin predictions by predicted probability (10 buckets: 0.0–0.1, 0.1–0.2, …, 0.9–1.0).
- For each bucket, compute the actual fraction of attacker emails.
- Plot predicted vs. actual. Perfect calibration = diagonal.
- Systematic overconfidence bites FPR. Systematic underconfidence misses catches.

**Expected result for iteration 1 of the fresh composer:** mild overconfidence at the high end (0.8+ bucket actually runs at 0.65–0.70 precision). Platt scaling via `CalibratedClassifierCV` handles this; it's baked into the composer training.

**Bar:** ECE ≤ 0.05 across all buckets, per release.

---

## Bypass accounting

When emails are excluded from scoring by Layer-0 rules (internal-to-internal, trusted-partner allowlists, system-generated mail, replies inside recipient-initiated threads — see `architecture_spec.md`), the eval must NOT count them as "caught real emails." They were never scored.

**Two separate metrics, always reported separately:**
1. **Bypass rate.** What fraction of real mail flow never reaches the scorer. Expected 40–70% in typical enterprise inboxes.
2. **Score-rate FPR and catch.** Computed only on emails that passed Layer 0 and were actually scored.

Reporting catch rate on "all real mail" including bypassed is a dishonest number that makes Chimera look much better than it is. We don't publish it.

---

## What a good eval report looks like

Every eval run produces an HTML report with the following structure. If any section is missing, the run is not considered complete.

1. **Headline.** One paragraph: what changed, what we tested, overall verdict.
2. **Ship-gate table.** Per-tier metrics against Gates 1–3, PASS/FAIL per line.
3. **Cross-writer distribution.** Box plot of catch@2%FPR across all 40 Enron writers. Callouts for best and worst.
4. **Short-email asymmetry.** Dedicated section with the table from Part 1, averaged across writers. This is the content-conditional composer's product claim.
5. **Ablation matrix.** Seven-detector + composer ablation.
6. **Reliability diagram.** Calibration curve + ECE.
7. **Bypass-layer stats.** Bypass rate, reason breakdown, sample bypassed vs. scored real emails.
8. **Confusion examples.** 10 highest-scored false positives and 10 lowest-scored false negatives. These are what you read to understand what the scorer is getting wrong.
9. **What changed from last run.** Diff against previous eval with 95% CIs. Regressions flagged in red.

Items 1–2 map to the old lean eval. Everything from 3 onward is new and is what the aggregation agent in the swarm produces.

---

## Honest floor: what we cannot measure

Some things the eval cannot prove, and we should say so out loud rather than hope the partner doesn't notice:

1. **True zero-day attackers.** We can only test against attack styles we can enumerate. A genuinely novel technique (dynamic per-recipient style adaptation from a compromised voice clone extracting intent from the recipient's own sent folder, say) is undetectable until we've seen an example.

2. **Base rate variability.** Enron BEC doesn't exist in the dataset because BEC wasn't a category in 2001. Our attacker corpus is synthetic. Real-world BEC is rarer and more heterogeneous than our corpus. The Phase 0 shadow-mode pilot is the first time we see real base rates.

3. **Recipient behavior under alert fatigue.** Our eval measures detector quality, not human response. A 95% catch rate is useless if users click banners through without reading. Phase 2 banner-useful rates are how we measure this, and only measurable in production.

4. **Long-tail styles.** 40 Enron writers is a sample. We'll miss some writing styles (non-native English, heavy jargon specialist registers, senior execs who write exclusively in one-line bullets). We'll learn these in pilot.

Writing this section honestly is part of Gate 5. If the pitch promises detection confidence we don't have, the pilot eats it in month 2.
