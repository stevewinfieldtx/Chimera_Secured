# Chimera Secured — Infrastructure Inventory

**Canonical as of:** 2026-04-17 (updated after CPA deploy confirmed live)
**Purpose:** The running inventory of everything Steve has deployed. Every Claude session should read this first and update it when anything changes. If a service exists, its URL and config should live here — not in Steve's head and not in Claude's context window.

**Rule for future-Claude sessions:** If you deploy something, add it here. If you're about to ask Steve "is X deployed" or "what's the URL of Y," check here first. If it's not here and Steve has mentioned it, ASK AND THEN WRITE IT DOWN. Do not re-ask in the next session.

**Key conventions on Steve's Railway setup:**
- Steve manually configures **Target Port 8888** on every service he creates. Services must bind to 8888, not $PORT.
- Railway projects may contain multiple services. Postgres is a plugin attached to the project, shared by services that reference it.
- Deploys are triggered by `git push` to the main branch of each service's repo.

---

## Railway — active services

### CPA (Communication Personality Analyzer) — **LIVE**
- **URL:** `https://chimerasecured.up.railway.app`
- **Project ID:** `eccc3d2d-6f71-40c5-ad10-8460363fa1bc`
- **Status (confirmed 2026-04-17):** Healthy. `/health` returns `{service: cpa, version: 0.1.0, db_healthy: true, background_corpus_size: 3325}`.
- **Endpoints verified live:**
  - `GET /health` → 200, ~920ms
  - `GET /cpp-status` → 200, ~340ms
  - `POST /score` → 200, ~540ms (returns `no_cpp` sentinel for non-enrolled users)
  - `POST /enroll`, `GET /labeling-queue`, `POST /label`, `GET /labeling-progress` — not yet hit in production but registered per `test_app_routes_registered` smoke test.
- **Code location (local):** `C:\Users\steve\Documents\Chimera_Secured\cpa\`
- **GitHub repo:** _[TO BE FILLED — presumably the Chimera_Secured repo]_
- **Postgres:** Attached to this Railway project. `DATABASE_URL` injected automatically.
- **Background corpus:** Seeded with 3,325 preprocessed Enron email bodies.
- **Port:** 8888 (hardcoded in `cpa/railway.json` start command to match Steve's Target Port convention).
- **Root Directory:** `cpa` (set in Railway service Settings → Source).

### TDE (Targeted Decomposition Engine)
- **URL:** `targeteddecomposition-production.up.railway.app`
- **Status:** Running. Ingests and serves content atoms.
- **Relevance to Chimera Secured v1:** NONE. TDE is not needed for v1.
- **GitHub repo:** _[TO BE FILLED]_
- **Railway project:** _[TO BE FILLED]_

### Enron collector
- **Status:** Deployed and has run. Corpus ingested into Postgres per `enron_collector/README.md`. One-shot job (`restartPolicyType: NEVER`).
- **URL:** _[N/A — job, not HTTP service]_
- **GitHub repo:** _[TO BE FILLED — per enron_collector/README, lives in its own repo separate from Chimera_Secured]_
- **Railway project:** _[TO BE FILLED — possibly same as CPA, sharing Postgres]_
- **Postgres tables:** `emails`, `attacker_emails`, `eval_runs`, view `writer_stats`.

---

## Railway services — still to build (per `implementation_plan.md` build order)

### CPA mirror service (Step 3)
- **Purpose:** Receives change-triggered CPP-E pushes from tenant-side CPAs.
- **Status:** Not started.
- **Code location:** Will live at `C:\Users\steve\Documents\Chimera_Secured\cpa_mirror\`.

### Chimera Secured scorer (Step 4)
- **Purpose:** Wraps CPA as D1, adds D3 (DLP) + D7 (metadata) + Bayesian composer + policy layer.
- **Status:** Not started.
- **Code location:** Will live at `C:\Users\steve\Documents\Chimera_Secured\chimera_scorer\`.

---

## CPA Railway environment variables

**Variables CPA actually reads** (from `cpa/src/config.py`):

| Variable | Purpose | Required? | Known value |
|---|---|---|---|
| `DATABASE_URL` | Postgres connection | Yes (set, Postgres attached) | Auto-injected by Railway Postgres plugin |
| `CPA_DATA_DIR` | Where local data lives | No, defaults to `./cpa_data` | Default |
| `CPA_ARTIFACTS_DIR` | Where classifier pickles live | No | Default |
| `CPA_MAX_ENROLL_EMAILS` | Cap on enrollment emails | No, default 2000 | Default |
| `CPA_MIN_EMAILS_FOR_HEAD` | Min per TW bucket | No, default 30 | Default |
| `CPA_BACKGROUND_CORPUS` | Path to background corpus pickle | No | Default |
| `CPA_MIRROR_URL` | Where to push CPPs on change | No (empty = mirroring disabled) | Not yet set — mirror service not built |
| `CPA_MIRROR_API_KEY` | Mirror auth | No | Not yet set |
| `CPA_LOG_LEVEL` | Log level | No, default INFO | Default |

**Variables currently on the Railway service but NOT used by CPA (stale from old Shield/TrueWriting stack):**
- `CHIMERA_EXPLAIN_ENABLED`, `CHIMERA_FPR_BUDGET`, `CHIMERA_MODE` — old scorer, not CPA
- `SHIELD_DB_PATH`, `SHIELD_PORT` — old Shield stack
- `TRUEWRITING_API_URL` — old stack
- `PER_WRITER_CAP`, `TRUNCATE_FIRST`, `LOG_EVERY` — belong to enron_collector, not CPA
- `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` — Phase 2+ feature, not wired

**Status:** Can be deleted from the CPA service to reduce noise, but not currently breaking anything. Steve to prune when convenient.

**Kept but not yet used (belong to Step 4 scorer):**
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL_ID`

---

## GitHub

- **GitHub account:** _[TO BE FILLED]_
- **Repos:**
  - Chimera_Secured (contains `cpa/` and will contain future `cpa_mirror/`, `chimera_scorer/`)
  - TDE — _[URL TBF]_
  - enron_collector — _[URL TBF]_

---

## Secrets & environment variables — where they live

Claude should NEVER see or ask for actual secret values. But it should know which secrets exist and where Steve manages them.

- **Railway env vars per service:** Steve sets these in the Railway dashboard per service.
- **Local `.env` file:** `C:\Users\steve\Documents\Chimera_Secured\.env` — used for local dev. Not committed (in `.gitignore`).
- **`.env.example`** is checked in and lists all variables that must be configured.

---

## What Claude should do when something is unclear

**DO:**
- Check this file first.
- If the info isn't here, ask Steve a specific question and then WRITE THE ANSWER HERE so the next session doesn't re-ask.
- When deploying something new, add a section to this file as part of the deploy checklist.

**DO NOT:**
- Re-ask questions across sessions.
- Treat "not in my context window" as "doesn't exist." If Steve mentions something is deployed, it's deployed; check this file, check Railway, or update this file — don't gaslight him.
- Ask Steve to make engineering decisions he hired Claude to make. He's the sales lead. Claude is the engineer.

---

## Revision log

- **2026-04-17 late afternoon** — CPA deploy confirmed live at `https://chimerasecured.up.railway.app`. All endpoints returning healthy. Background corpus seeded. Steve clarified he always configures Railway Target Port to 8888 — start command now hardcodes `--port 8888`. Deploy journey required 3 fixes: Root Directory set to `cpa`, `nixpacks.toml` deleted (was breaking pip), start command changed to `cd src && uvicorn app:app --port 8888` (flat imports didn't resolve from /app, and port had to match 8888).
- **2026-04-17 mid-afternoon** — File created. Inventory was incomplete.
