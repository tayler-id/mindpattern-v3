#!/usr/bin/env bash
# Knowledge compiler: runs after the daily pipeline completes.
# Standalone — if this crashes, the pipeline already succeeded.
#
# Usage:
#   ./knowledge/run.sh                    # compile today
#   ./knowledge/run.sh --date 2026-04-05  # compile specific date
#   ./knowledge/run.sh --lookback 14      # look back 14 days

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

DB="${PROJECT_DIR}/data/ramsay/memory.db"
VAULT="${PROJECT_DIR}/data/ramsay/mindpattern"

if [ ! -f "$DB" ]; then
    echo "ERROR: Database not found at $DB"
    exit 1
fi

echo "=== Knowledge Compiler ==="
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "DB: $DB"
echo "Vault: $VAULT"
echo ""

# Step 1: Compile findings into concept pages
echo "--- COMPILE ---"
python3 -m knowledge.compile --db "$DB" --vault "$VAULT" "$@"

# Step 2: Lint knowledge base (when lint.py exists)
if [ -f "${SCRIPT_DIR}/lint.py" ]; then
    echo ""
    echo "--- LINT ---"
    python3 -m knowledge.lint --vault "$VAULT" || echo "WARN: Lint reported issues"
fi

# Step 3: Update qmd search index (if qmd is installed)
if command -v qmd &>/dev/null; then
    echo ""
    echo "--- SEARCH INDEX ---"
    qmd update && qmd embed
fi

echo ""
echo "=== Done ==="
