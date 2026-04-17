# Chimera Secured — Pilot Readiness Workspace

This folder is the clean working space for getting Chimera Secured from "the research stack had promising signals" to "I honestly think this will work in a real pilot." We have two partners lined up — Rain Networks (who can put us in front of up to 60,000 seats via their downstream partners, with actual pilot size determined by which of those partners opt in) and a second partner — ready to engage once the product is close enough to test in the wild.

It is deliberately separate from the older experimental stack at `...documents\truewriting\`, which is **reference material only**. That code was built against a flawed plan (see the Kimi AI review), and we are not porting it. We are building fresh, informed by everything the old stack taught us and guided by Kimi's structural critique applied to the actual problem we are solving.

## Read `implementation_plan.md` first

If you're a new Claude session or Steve coming back after a few days, `implementation_plan.md` is the anchor document. It has the current v1 scope, what's real vs. aspirational, what's been built, and what's next. Everything else in this folder is supporting material.

## The one-line product statement

Chimera Secured detects Business Email Compromise by comparing each email against a per-user Communication Personality Profile (CPP-E) that fingerprints how the real inbox owner writes, with the DLP content category acting as a contextual modulator — weak style evidence matters a lot when the email contains a wire instruction, and barely matters at all when the email is asking what's for lunch.

## The sovereignty constraint, in one paragraph

Email bodies never leave the customer environment. Not to our servers, not to a co-located service we control, not transiently. The CPP-E (an abstract fingerprint with no reconstructible email content) is the only object that crosses the tenant boundary, and it does so only when its content hash changes, to a Railway-side CPA mirror the tenant can disable. Scoring happens inside the tenant, against the local CPP-E. This is architectural, not a policy claim.

## What's in this folder

- **`implementation_plan.md`** — the anchor. Read first.
- **`README.md`** — this file.
- **`pilot_readiness_plan.md`** — five gates and a phased pilot rollout. Older framing; `implementation_plan.md` wins where they disagree.
- **`eval_strategy.md`** — Enron cross-writer plan and adversarial tiers. Still correct.
- **`architecture_spec.md`** — Phase 2+ north star. V1 uses a narrower scope; see `implementation_plan.md`.
- **`scoring_redesign.md`** — Kimi's scoring principles translated onto our problem. Composer math and content-category priors are still correct. V1 uses D1, D3, D7 only.
- **`cpa/`** — the Communication Personality Analyzer service. Step 1 of the build order. Working, tested.
- **`enron_collector/`** — already working on Railway. Streams the CMU Enron corpus into Railway Postgres for cross-writer eval. Kept as-is.

## Canonical names

- **WinTech Partners** — the parent platform company.
- **NYN Impact** — operating company, owns Chimera Secured.
- **CPA** — Communication Personality Analyzer. The engine that produces CPPs.
- **CPP-E / CPP-V / CPP-P** — CPP sourced from email / video / podcast.
- **TDE** — Targeted Decomposition Engine. Content atoms. Not needed for Chimera Secured v1.
- **TrueGraph** — relationship graph engine. Future.
- **TW+ / TW0 / TW-** — formal / average / casual buckets in the TW system.

## Guiding principles

1. **Honest over optimistic.** "I think this will work" is only said when the eval supports it across writers, not just one.
2. **Sovereign by architecture.** Email bodies stay in-tenant. Forever.
3. **Detection before enforcement.** The first pilot phase is log-only. We earn blocking rights with real-world FPR data.
4. **Catch the right things.** Content category tells us how much the style signal matters.
5. **Parallel everywhere possible.** Evaluation is the bottleneck. Scale it with agent swarms.
6. **Cut first, add later.** V1 is intentionally narrow. Phase 2 expands only when a pilot proves the pull.
