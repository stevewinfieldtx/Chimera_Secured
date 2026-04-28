# ClearSignals — Voice Agents

## Status: Scaffolded — awaiting content

To activate voice agents for ClearSignals:

1. Write TDE ingestion documents in `tde-ingestion/` and ingest into a `clearsignals` collection
2. Write agent prompts in `prompts/` (one per role — sales.md, tech-support.md, etc.)
3. Configure agent JSON files in `agents/` (copy from `_template` and fill in)
4. Run `node ../../agent-factory.js --config agents/sales.json`
