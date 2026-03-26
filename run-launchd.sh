#!/bin/bash
# Wrapper for launchd — runs the pipeline with concurrency guard.
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

# Only run between 6 AM and 12 PM (prevents midnight/late-night triggers)
HOUR=$(date +%H)
if [ "$HOUR" -lt 6 ] || [ "$HOUR" -ge 12 ]; then
    log "SKIP: Outside run window (hour=$HOUR, allowed=06-11)"
    exit 0
fi

# Atomic lock acquisition via mkdir (atomic on all POSIX systems)
LOCK_DIR="${LOCK}.d"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    # Lock dir exists — check if the owning process is still alive
    LOCK_PID=$(cat "$LOCK" 2>/dev/null)
    if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
        log "SKIP: Pipeline is running (pid=$LOCK_PID)"
        exit 0
    else
        log "WARN: Stale lock (pid=$LOCK_PID not running), reclaiming"
        rm -f "$LOCK"
        rmdir "$LOCK_DIR" 2>/dev/null
        if ! mkdir "$LOCK_DIR" 2>/dev/null; then
            log "SKIP: Lost lock race after stale cleanup"
            exit 0
        fi
    fi
fi

log "START: Beginning pipeline for $TODAY"

# Write lock with our PID
echo "$$" > "$LOCK"

# Keep Mac awake during run
caffeinate -i -s -w "$$" &
CAFF_PID=$!

/opt/homebrew/bin/python3 run.py "$@"
EXIT_CODE=$?

# Mark today as done (even on failure — don't retry automatically)
touch "$MARKER"

# Clean up
rm -f "$LOCK"
rmdir "$LOCK_DIR" 2>/dev/null
kill "$CAFF_PID" 2>/dev/null

log "DONE: Pipeline finished with exit code $EXIT_CODE"
exit $EXIT_CODE
