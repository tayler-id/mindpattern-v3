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
LOGFILE="reports/launchd-decisions.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOGFILE"
    echo "$(date '+%H:%M:%S') $1"
}

log "=== Launchd triggered ==="
log "Date: $TODAY"
log "User: $(whoami)"
log "Mac awake since: $(sysctl -n kern.waketime 2>/dev/null || echo unknown)"
log "Lock file: $([ -f "$LOCK" ] && echo "EXISTS (pid=$(cat "$LOCK" 2>/dev/null))" || echo "none")"
log "Marker file: $([ -f "$MARKER" ] && echo "EXISTS" || echo "none")"

# Skip if already ran today
if [ -f "$MARKER" ]; then
    log "SKIP: Pipeline already ran today ($TODAY)"
    exit 0
fi

# Check for stale lock (process no longer running)
if [ -f "$LOCK" ]; then
    LOCK_PID=$(cat "$LOCK" 2>/dev/null)
    if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
        log "SKIP: Pipeline is running (pid=$LOCK_PID)"
        exit 0
    else
        log "WARN: Stale lock file (pid=$LOCK_PID not running), removing"
        rm -f "$LOCK"
    fi
fi

# Check FDA for python3
if ! /opt/homebrew/bin/python3 -c "
import sqlite3, os
db_path = os.path.expanduser('~/Library/Messages/chat.db')
try:
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.execute('SELECT 1 FROM message LIMIT 1')
    conn.close()
except Exception as e:
    print(f'FDA_CHECK_FAILED: {e}')
    exit(1)
" 2>/dev/null; then
    log "ERROR: Python3 cannot read Messages.db — Full Disk Access not granted"
    log "FIX: System Settings → Privacy & Security → Full Disk Access → add /opt/homebrew/opt/python@3.14/bin/python3.14"
    # Continue anyway — pipeline will work except iMessage gates
fi

log "START: Beginning pipeline for $TODAY"

# Write lock with our PID
echo $$ > "$LOCK"

# Keep Mac awake during run
caffeinate -i -s -w $$ &
CAFF_PID=$!

/opt/homebrew/bin/python3 run.py "$@"
EXIT_CODE=$?

# Mark today as done (even on failure — don't retry automatically)
touch "$MARKER"

# Clean up
rm -f "$LOCK"
kill "$CAFF_PID" 2>/dev/null

log "DONE: Pipeline finished with exit code $EXIT_CODE"
exit $EXIT_CODE
