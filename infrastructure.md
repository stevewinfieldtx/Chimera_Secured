# Chimera Secured — Infrastructure Inventory

**Canonical as of:** 2026-04-17
**Purpose:** The running inventory of everything Steve has deployed. Every Claude session should read this first and update it when anything changes. If a service exists, its URL and config should live here — not in Steve's head and not in my context window.

**Rule for future-Claude sessions:** If you deploy something, add it here. If you're about to ask Steve "is X deployed" or "what's the URL of Y," check here first. If it's not here and Steve has mentioned it, ASK AND THEN WRITE IT DOWN. Do not re-ask in the next session.

---

## Railway services — known

### TDE (Targeted Decomposition Engine)
- **URL:** `targeteddecomposition-production.up.railway.app`
- **Status:** Running. Ingests and serves content atoms.
- **Relevance to Chimera Secured v1:** NONE. TDE is not needed for v1. Chimera Secured v1 uses the CPA service for stylometric fingerprints, not TDE.
- **GitHub repo:** _[TO BE FILLED BY STEVE]_
- **Railway project:** _[TO BE FILLED BY STEVE]_

### Enron collector
- **Status:** Deployed and has run. Corpus ingested into Postgres per `enron_collector/README.md`. This is a one-shot job service (`restartPolicyType: NEVER`) — runs on deploy, exits.
- **URL:** _[N/A — it's a job, not an HTTP service]_
- **GitHub repo:** _[TO BE FILLED BY STEVE — per the enron_collector README, it should live in its own repo separate from Chimera_Secured]_
- **Railway project:** _[TO BE FILLED BY STEVE]_
- **Postgres:** Has the Enron corpus in tables `emails`, `attacker_emails`, `eval_runs`, view `writer_stats`. Attached via Railway Postgres plugin with `DATABASE_URL` auto-injected.

### CPA (Communication Personality Analyzer)
- **Status:** _[TO BE VERIFIED — Steve indicated "I have it set up on Railway" on 2026-04-17 but no prior session captured the URL or config]_
- **Code location (local):** `C:\Users\steve\Documents\Chimera_Secured\cpa\`
- **Code status (local):** 20/20 smoke tests passing as of 2026-04-17.
- **URL:** _[TO BE FILLED]_
- **GitHub repo:** _[TO BE FILLED]_
- **Railway project:** _[TO BE FILLED]_
- **Postgres:** Shares the Enron Postgres? Or has its own? _[TO BE CLARIFIED]_
- **Background corpus seeded:** _[TO BE VERIFIED — if CPA is running, `/health` should report `background_corpus_size > 0`. If not, run `scripts/seed_background.py` on Railway.]_

---

## Railway services — still to build (per `implementation_plan.md` build order)

### CPA mirror service (Step 3)
- **Purpose:** Receives change-triggered CPP-E pushes from tenant-side CPAs.
- **Status:** Not started.
- **Code location:** Will live at `C:\Users\steve\Documents\Chimera_Secured\cpa_mirror\` when built.

### Chimera Secured scorer (Step 4)
- **Purpose:** Wraps CPA as D1, adds D3 (DLP) + D7 (metadata) + Bayesian composer + policy layer.
- **Status:** Not started.
- **Code location:** Will live at `C:\Users\steve\Documents\Chimera_Secured\chimera_scorer\` when built.

---

## GitHub

- **GitHub account:** _[TO BE FILLED]_
- **Repos currently in use for Chimera Secured work:**
  - _[TO BE FILLED — Chimera_Secured repo URL, enron_collector repo URL, TDE repo URL, others]_

---

## Secrets & environment variables — where they live

Claude should NEVER see or ask for actual secret values. But it should know which secrets exist and where Steve manages them.

- **Railway env vars per service:** Steve sets these in the Railway dashboard per service.
- **Local `.env` file:** `C:\Users\steve\Documents\Chimera_Secured\.env` — used for local dev. Not committed (in `.gitignore`).
- **`.env.example`** is checked in and lists all variables that must be configured, with placeholder values.

Variables Chimera Secured components need (full list in `.env.example`):
- `DATABASE_URL` — auto-set by Railway Postgres plugin
- `TENANT_ID`, `TENANT_NAME`
- `M365_TENANT_ID`, `M365_CLIENT_ID`, `M365_CLIENT_SECRET`, `M365_TARGET_USER` (when M365 Graph integration lands)
- `IMAP_*` (Hotmail fallback path)
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL_ID`
- `CPA_API_URL`, `CPA_API_KEY`
- `CPA_MIRROR_URL`, `CPA_MIRROR_API_KEY`

---

## What Claude should do when something is unclear

**DO:**
- Check this file first.
- If the info isn't here, ask Steve a specific question ("What's the Railway URL for the CPA service?") and then WRITE THE ANSWER HERE so the next session doesn't re-ask.
- When deploying something new, add a section to this file as part of the deploy checklist.

**DO NOT:**
- Re-ask questions across sessions. Steve's answer in session 4 is exactly as valid in session 5 if you write it down.
- Treat "not in my context window" as the same as "doesn't exist." If Steve mentions something is deployed, it's deployed; check this file, check Railway, or update this file — don't gaslight him.
- Ask Steve to make engineering decisions he hired Claude to make. He's the sales lead. Claude is the engineer. If there's a choice between two technical options, Claude picks the one that matches the plan and explains briefly; it doesn't ask Steve to pick.

---

## Revision log

- **2026-04-17** — File created. Inventory is incomplete — several fields marked `[TO BE FILLED]`. Next session (or continued session) should fill them in by asking Steve targeted questions and updating this file immediately.
