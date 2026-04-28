# TDE Ingestion Documents — Chimera Secured Collection

These documents are structured for ingestion into the Targeted Decomposition Engine (TDE) as the `chimera_secured` collection. The voice agent uses the Orchestrator's `/respond` endpoint to retrieve grounded answers from this collection in real time during phone conversations.

## Documents

| File | Content | Primary TDE Dimensions |
|------|---------|----------------------|
| `01-product-overview.md` | What Chimera Secured is, the problem it solves, threat coverage, target audience | persona, buying_stage, emotional_driver |
| `02-how-cpa-works.md` | Enrollment, feature extraction, TW bucketing, XGBoost classifiers, scoring pipeline, data sovereignty | evidence_type, credibility, persona |
| `03-voice-profiles.md` | Voice profile generation, exportable style guides, value for exec comms | buying_stage, economic_driver |
| `04-deployment-and-integration.md` | Docker deployment, Azure AD setup, M365 integration, API access, MSP management | persona (partner_msp, direct_cto), status_quo_pressure |
| `05-pilot-program.md` | Pilot phases (shadow → warn → enforce), success criteria, timeline, partner structure | buying_stage, economic_driver, industry |
| `06-faq-and-objection-handling.md` | Common questions and detailed answers — product, security, privacy, technical, MSP-specific | All dimensions — this is the broadest document |
| `07-competitive-positioning.md` | Market gap, differentiation from Defender/Proofpoint/Mimecast, ROI, positioning | emotional_driver, economic_driver, status_quo_pressure |
| `08-conversation-scenarios.md` | Response templates for common conversation paths — technical, non-technical, objections, demos | persona, buying_stage, emotional_driver |

## Ingestion Notes

These documents are written in a style optimized for TDE atomic decomposition:

- **Self-contained paragraphs**: Each paragraph states a complete fact or argument. TDE should produce clean AIUs of 8-120 words without needing to stitch across paragraphs.
- **No cross-references**: Documents do not refer to each other with "as mentioned in..." style links. Each document stands alone.
- **Explicit rather than implicit**: Numbers, names, and claims are stated directly rather than implied by context.
- **Persona coverage**: Content is written to serve multiple audience types — MSP partners (partner_msp), CISOs (direct_ciso), CTOs (direct_cto), CFOs (direct_cfo), and technical evaluators.
- **Buying stage coverage**: Content ranges from awareness (what is BEC, why does this matter) through evaluation (how does it work technically) to decision (pilot structure, ROI, deployment effort).

## Collection Configuration

When creating the TDE collection, use:

```json
{
  "collection_id": "chimera_secured",
  "name": "Chimera Secured Product Knowledge",
  "description": "Complete product knowledge base for the Chimera Secured BEC detection platform — used by the voice agent to answer customer and MSP questions.",
  "tags": {
    "product": "chimera_secured",
    "version": "v1_pilot",
    "audience": ["partner_msp", "direct_ciso", "direct_cto", "direct_cfo", "technical"]
  }
}
```

## Ingestion Command

Via the Orchestrator API:

```bash
# Ingest all documents into the chimera_secured collection
for doc in 01-product-overview.md 02-how-cpa-works.md 03-voice-profiles.md \
           04-deployment-and-integration.md 05-pilot-program.md \
           06-faq-and-objection-handling.md 07-competitive-positioning.md \
           08-conversation-scenarios.md; do
  curl -X POST http://localhost:8500/intel \
    -H "Content-Type: application/json" \
    -d "{
      \"collection_id\": \"chimera_secured\",
      \"content\": $(cat "$doc" | jq -Rs .),
      \"source\": \"$doc\"
    }"
done
```
