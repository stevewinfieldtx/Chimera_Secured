# CPA Quickstart — From Zero to Running in 30 Minutes

This guide takes you from a fresh clone to a working CPA deployment with a live dashboard. Every command is copy-pasteable. No branching, no "if you chose option A" — just follow the steps.

**What you'll have at the end:** A running CPA instance that can enroll users from Microsoft 365 mailboxes, score emails for authenticity, generate voice profiles, and serve an admin dashboard.

**What you need before you start:**
- Docker and Docker Compose installed ([get Docker](https://docs.docker.com/get-docker/))
- An Azure AD tenant with admin access (for Graph API email access)
- 30 minutes

---

## Step 1: Clone and configure

```bash
cd ~/projects   # or wherever you keep repos
git clone https://github.com/wintechpartners/chimera-secured.git
cd chimera-secured/cpa
cp .env.example .env
```

Open `.env` in any editor. You need to fill in **4 values** (everything else has working defaults):

```
CPA_API_KEY=<pick any strong random string — this protects your API>
AZURE_TENANT_ID=<from Step 2>
AZURE_CLIENT_ID=<from Step 2>
AZURE_CLIENT_SECRET=<from Step 2>
```

Don't close the file yet — get the Azure values from Step 2 first.

---

## Step 2: Create the Azure AD app registration

This gives CPA permission to read sent emails from your tenant's mailboxes.

1. Go to [Azure Portal → App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. Click **New registration**
   - Name: `Chimera Secured CPA`
   - Supported account types: **Accounts in this organizational directory only**
   - Redirect URI: leave blank
   - Click **Register**
3. On the app's Overview page, copy:
   - **Application (client) ID** → paste into `.env` as `AZURE_CLIENT_ID`
   - **Directory (tenant) ID** → paste into `.env` as `AZURE_TENANT_ID`
4. Go to **Certificates & secrets** → **New client secret**
   - Description: `CPA pilot`
   - Expires: 6 months (or your preference)
   - Click **Add**, copy the **Value** (not the Secret ID) → paste into `.env` as `AZURE_CLIENT_SECRET`
5. Go to **API permissions** → **Add a permission**
   - Select **Microsoft Graph** → **Application permissions**
   - Search for and add: `Mail.Read`
   - Click **Add permissions**
6. Click **Grant admin consent for [your org]** → **Yes**

That's it. Your `.env` should now have all 4 values filled in. Save it.

---

## Step 3: Start everything

```bash
docker compose up -d
```

This builds the CPA container, starts PostgreSQL, seeds the background corpus automatically on first boot, and starts the API server. First build takes 3-5 minutes (downloading Python packages). Subsequent starts take seconds.

Watch the logs to confirm it's healthy:

```bash
docker compose logs -f cpa
```

You should see:
```
>>> Background corpus not found...
>>> Generating synthetic corpus (first run only)...
>>> Corpus seeded successfully.
>>> Starting CPA service...
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Press Ctrl+C to stop watching logs (the service keeps running).

---

## Step 4: Verify it works

Hit the health endpoint:

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "service": "cpa",
  "version": "0.1.0",
  "db_healthy": true,
  "background_corpus_size": 500
}
```

If `db_healthy` is `true` and `background_corpus_size` is 500, you're good. Open the dashboard:

```
http://localhost:8000/dashboard
```

---

## Step 5: Enroll your first user

In the dashboard:

1. Set the **API Key** field to whatever you put in `CPA_API_KEY` in your `.env`
2. Click **Enroll** in the sidebar
3. Enter an email address from your tenant (someone with 30+ sent emails)
4. Click **Enroll from Graph**

Enrollment pulls sent emails via the Graph API, preprocesses them, trains the behavioral classifiers, and builds the communication personality profile. This takes 30-120 seconds depending on email volume. The dashboard shows progress.

When complete, you'll see: buckets trained, training email count, and a CPP version string.

**Or via API:**
```bash
curl -X POST http://localhost:8000/enroll-from-graph \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"user_email": "user@yourdomain.com"}'
```

---

## Step 6: Score a test email

In the dashboard, click **Score Email** in the sidebar:

1. Enter the enrolled user's email as the **User Email**
2. Enter a recipient email (someone they've emailed before)
3. Paste an email body — either a real email from that user, or a fake one
4. Click **Score**

Results:
- **p_authentic > 0.7** = Authentic (consistent with this user's writing style)
- **p_authentic 0.4-0.7** = Uncertain (some anomalies detected)
- **p_authentic < 0.4** = Suspicious (does not match this user's patterns)

**Try the test:** Score a real email from the user (should score high), then score something you wrote pretending to be them (should score lower).

**Or via API:**
```bash
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{
    "tenant_id": "default",
    "user_email": "user@yourdomain.com",
    "recipient_email": "recipient@example.com",
    "email_body": "Paste the email text here"
  }'
```

---

## Step 7: Generate a voice profile

In the dashboard, click **Voice Profile** in the sidebar:

1. Enter the enrolled user's email
2. Click **Generate**

This produces a 10-section writing style guide derived from the user's behavioral profile. Click **Copy Full Profile to Clipboard** and paste it into ChatGPT, Gemini, or any LLM as a system instruction — that LLM will now write in the user's voice.

---

## You're done

The system is running. From here:

- **Enroll more users** — repeat Step 5 for each mailbox you want to profile
- **Check profile status** — Dashboard → Profiles → enter email
- **Review labels** — Dashboard → Labels → review auto-classifications
- **Monitor** — `docker compose logs -f cpa` for live logs
- **Stop** — `docker compose down` (data persists in Docker volumes)
- **Restart** — `docker compose up -d` (instant, no re-seeding)

---

## API Reference (Quick)

All endpoints except `/health` and `/dashboard` require the `X-API-Key` header.

| Method | Endpoint | What it does |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/dashboard` | Admin UI |
| POST | `/enroll` | Enroll from provided emails |
| POST | `/enroll-from-graph` | Enroll by pulling from Graph API |
| POST | `/score` | Score one email |
| GET | `/cpp-status?tenant_id=X&user_email=Y` | Check profile status |
| GET | `/voice-profile?tenant_id=X&user_email=Y` | Generate voice profile |
| GET | `/labeling-queue?tenant_id=X&user_id=Y` | View labeling queue |
| POST | `/label` | Set/override a label |
| GET | `/labeling-progress?tenant_id=X&user_id=Y` | Labeling stats |
| GET | `/docs` | Interactive API docs (Swagger) |

---

## Troubleshooting

**"Background corpus has 0 texts"** — The auto-seed didn't run. Manually trigger it:
```bash
docker compose exec cpa python /app/scripts/seed_background.py --generate --size 500
```

**"Azure AD credentials not configured"** — Check your `.env` file has AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET filled in, then restart: `docker compose restart cpa`

**"Invalid or missing API key"** — Add the `X-API-Key` header to your request, or enter the key in the dashboard's config bar.

**"Not enough usable emails after preprocessing: X < 30"** — The user doesn't have enough sent emails (need 30+ with 15+ words each). Try a more active mailbox.

**"Failed to fetch emails from Graph"** — Check that your Azure AD app has `Mail.Read` application permission with admin consent. Verify the user exists in the tenant.

**Container won't start** — Check logs: `docker compose logs cpa`. Most common issue: `.env` file missing or malformed.

**Reset everything** — `docker compose down -v` removes all data. `docker compose up -d` starts fresh.
