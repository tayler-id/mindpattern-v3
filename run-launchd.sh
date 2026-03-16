#!/bin/bash
# Wrapper for launchd — /bin/bash has Full Disk Access, python3 may not.
# This ensures Messages.db is readable for iMessage approval gates.
#
# Idempotent: checks if today's run already completed before starting.
# Safe to trigger on schedule AND on wake — won't double-run.

cd /Users/taylerramsay/Projects/mindpattern-v3

TODAY=$(date +%Y-%m-%d)
LOCK="/tmp/mindpattern-pipeline.lock"
MARKER="/tmp/mindpattern-ran-${TODAY}"

# Skip if already ran today
if [ -f "$MARKER" ]; then
    echo "$(date '+%H:%M:%S') Pipeline already ran today ($TODAY), skipping"
    exit 0
fi

# Skip if currently running
if [ -f "$LOCK" ]; then
    echo "$(date '+%H:%M:%S') Pipeline is already running (lock file exists), skipping"
    exit 0
fi

echo "$(date '+%H:%M:%S') Starting pipeline for $TODAY"

# Keep Mac awake during run
caffeinate -i -s -w $$ &
CAFF_PID=$!

/opt/homebrew/bin/python3 run.py "$@"
EXIT_CODE=$?

# Mark today as done (even on failure — don't retry automatically)
touch "$MARKER"

kill "$CAFF_PID" 2>/dev/null
exit $EXIT_CODE
