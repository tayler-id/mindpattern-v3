#!/bin/bash
# Wrapper for launchd — runs the pipeline with concurrency guard.
#
# Idempotent: checks if today's run already completed before starting.
# Safe to trigger on schedule AND on wake — won't double-run.

cd /Users/taylerramsay/Projects/mindpattern-v3

TODAY=$(date +%Y-%m-%d)
LOCK="/tmp/mindpattern-pipeline.lock"
MARKER_DIR="${MP_RAN_MARKER_DIR:-/tmp}"
MARKER="${MARKER_DIR}/mindpattern-ran-${TODAY}"
SYNC_MARKER="${MARKER_DIR}/mindpattern-synced-${TODAY}"
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
log "Delivery marker: $([ -f "$MARKER" ] && echo "EXISTS" || echo "none")"
log "Sync marker: $([ -f "$SYNC_MARKER" ] && echo "EXISTS" || echo "none")"

# Skip only when delivery and Fly sync both completed today.
if [ -f "$MARKER" ] && [ -f "$SYNC_MARKER" ]; then
    log "SKIP: Pipeline already delivered and synced today ($TODAY)"
    exit 0
fi

if [ -f "$MARKER" ] && [ ! -f "$SYNC_MARKER" ]; then
    log "Delivery marker exists but sync marker is missing — retrying to complete sync"
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

# Pull latest code from main before running
BRANCH=$(git branch --show-current 2>/dev/null)
if [ "$BRANCH" = "main" ]; then
    log "Pulling latest main..."
    git pull origin main --ff-only >> "$LOGFILE" 2>&1 || log "WARN: git pull failed — running with local code"
else
    log "WARN: Not on main branch ($BRANCH) — skipping pull"
fi

# Keep Mac awake during run
caffeinate -i -s -w "$$" &
CAFF_PID=$!

/Users/taylerramsay/Projects/mindpattern-v3/.venv/bin/python3 run.py "$@"
EXIT_CODE=$?

# NOTE: the ran-marker is NOT touched here. The deliver phase writes
# "$MARKER" only when the newsletter is confirmed delivered, so a crash or a
# send failure leaves it absent and the next hourly window (08-11) retries.
# Before this (2026-06-13) the marker was set even on instant startup crash,
# turning a one-second bug into an all-day outage. Receipts make retries safe.
if [ -f "$MARKER" ] && [ -f "$SYNC_MARKER" ]; then
    log "Newsletter delivered and synced — $TODAY marked done"
elif [ -f "$MARKER" ]; then
    log "WARN: newsletter delivered but sync marker missing (exit=$EXIT_CODE) — backup window will retry"
else
    log "WARN: no delivery this run (exit=$EXIT_CODE) — backup window will retry"
fi

# Clean up
rm -f "$LOCK"
rmdir "$LOCK_DIR" 2>/dev/null
kill "$CAFF_PID" 2>/dev/null

log "DONE: Pipeline finished with exit code $EXIT_CODE"
exit $EXIT_CODE
