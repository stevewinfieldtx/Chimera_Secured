# Voice Agent Factory

One command to provision a fully configured ElevenLabs voice agent with Twilio phone number and TDE-backed knowledge retrieval. Reusable across every WinTech product.

## Structure

```
voice-agent-factory/
  agent-factory.js          ← The factory script (product-agnostic)
  .env.example              ← API credentials
  bridge/                   ← Shared webhook service (one instance serves all agents)
    server.js
    Dockerfile
  applications/
    chimera-secured/        ← ✓ LIVE — fully built out
      agents/
        product-specialist.json
        tech-support.json
        sales.json
      prompts/
        product-specialist.md
        tech-support.md
        sales.md
      tde-ingestion/
        01-product-overview.md
        02-how-cpa-works.md
        ... (8 docs total)
    clearsignals/           ← Scaffolded — awaiting content
    oppintelai/             ← Scaffolded — awaiting content
    decision-apps/          ← Scaffolded — awaiting content
    wintech/                ← Scaffolded — for cross-portfolio agents
    _template/              ← Blank template for new products
```

## How it works

Every voice agent follows the same pattern:

1. **TDE ingestion docs** — structured content about the product, ingested into a TDE collection
2. **System prompt** — defines the agent's persona, tone, guardrails, and escalation rules
3. **Agent config** — JSON file with the product, role, voice, collection ID, phone number, and bridge URL
4. **One command** — the factory reads the config and provisions everything via API

The bridge service is shared. It routes each agent's knowledge queries to the right TDE collection based on the `collection_id` in the request. One bridge serves Chimera Secured, ClearSignals, OppIntelAI, and every future product.

## Quick start

```bash
cd voice-agent-factory
cp .env.example .env
# Fill in ELEVENLABS_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN

# See what's available
node agent-factory.js --list

# Preview what would happen (no API calls)
node agent-factory.js --config applications/chimera-secured/agents/product-specialist.json --dry-run

# Deploy it
node agent-factory.js --config applications/chimera-secured/agents/product-specialist.json
```

## Adding a new product

When you build a new application, AI generates the content and you run one command:

1. **Create the application folder:**
   ```bash
   cp -r applications/_template applications/your-product
   ```

2. **Write TDE ingestion docs** — put them in `applications/your-product/tde-ingestion/`. Structure content as self-contained paragraphs optimized for atomic decomposition. AI can generate these from product docs, specs, pitch decks, etc.

3. **Ingest into TDE** — create a collection and load the docs:
   ```bash
   curl -X POST http://localhost:8500/intel \
     -H "Content-Type: application/json" \
     -d '{"collection_id": "your_product", "content": "...", "source": "01-overview.md"}'
   ```

4. **Write agent prompts** — one per role. Save to `applications/your-product/prompts/`. Define persona, tone, guardrails, escalation.

5. **Configure agent JSON** — copy `_template/agents/example.json` into your agents folder, fill in the product slug, collection ID, voice, bridge URL, and phone number.

6. **Deploy:**
   ```bash
   node agent-factory.js --config applications/your-product/agents/sales.json
   ```

That's it. The bridge already knows how to route to the new collection. No code changes needed.

## Applications

| Application | Status | TDE Collection | Agents |
|-------------|--------|---------------|--------|
| chimera-secured | Live | `chimera_secured` | product-specialist, tech-support, sales |
| clearsignals | Scaffolded | `clearsignals` | — |
| oppintelai | Scaffolded | `oppintelai` | — |
| decision-apps | Scaffolded | `decision_apps` | — |
| wintech | Scaffolded | `wintech_general` | — |

## Bridge deployment

The bridge is a single Node.js service that all agents share:

```bash
cd bridge
cp .env.example .env
# Set ORCHESTRATOR_URL and BRIDGE_SECRET
npm install && npm start
```

Or with Docker:
```bash
docker build -t voice-agent-bridge .
docker run -d -p 3100:3100 -e ORCHESTRATOR_URL=http://your-orchestrator:8500 voice-agent-bridge
```

Deploy it once, publicly accessible, and point all agent configs at it.
