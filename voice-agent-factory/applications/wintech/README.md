# WinTech Partners — Voice Agents

## Status: Scaffolded — awaiting content

General WinTech agents that can speak across the full portfolio — Chimera Secured,
ClearSignals, OppIntelAI, Decision Apps. These agents would query multiple TDE
collections or a combined `wintech_general` collection.

To activate:

1. Write TDE ingestion documents covering the WinTech portfolio in `tde-ingestion/`
2. Write agent prompts in `prompts/`
3. Configure agent JSON files in `agents/`
4. Run `node ../../agent-factory.js --config agents/<role>.json`
