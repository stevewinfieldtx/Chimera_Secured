#!/bin/bash
set -e

echo "=== CPA Entrypoint ==="
echo "CPA_DATA_DIR=${CPA_DATA_DIR:-/app/cpa_data}"

# Auto-seed background corpus if it doesn't exist
CORPUS_PATH="${CPA_BACKGROUND_CORPUS:-${CPA_DATA_DIR:-/app/cpa_data}/background_corpus.pkl}"

if [ ! -f "$CORPUS_PATH" ]; then
    echo ">>> Background corpus not found at $CORPUS_PATH"
    echo ">>> Generating synthetic corpus (first run only)..."
    cd /app
    python scripts/seed_background.py --generate --size 500
    echo ">>> Corpus seeded successfully."
else
    echo ">>> Background corpus found at $CORPUS_PATH"
fi

# Start the app
echo ">>> Starting CPA service..."
cd /app/src
exec uvicorn app:app --host 0.0.0.0 --port 8000 --workers "${CPA_WORKERS:-1}"
