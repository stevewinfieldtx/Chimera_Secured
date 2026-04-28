# OppIntelAI — Voice Agents

## Status: Scaffolded — awaiting content

To activate voice agents for OppIntelAI:

1. Write TDE ingestion documents in `tde-ingestion/` and ingest into an `oppintelai` collection
2. Write agent prompts in `prompts/` (one per role)
3. Configure agent JSON files in `agents/`
4. Run `node ../../agent-factory.js --config agents/<role>.json`
