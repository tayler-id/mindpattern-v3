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

# Check if main has new commits since the marker was written (merged PRs).
# If so, clear the marker so the pipeline re-runs with the new code.
if [ -f "$MARKER" ]; then
    MARKER_TS=$(stat -f %m "$MARKER" 2>/dev/null || echo 0)
    # Fetch without merging to see if remote main moved
    git fetch origin main --quiet 2>/dev/null || true
    LATEST_COMMIT_TS=$(git log -1 --format=%ct origin/main 2>/dev/null || echo 0)
    if [ "$LATEST_COMMIT_TS" -gt "$MARKER_TS" ]; then
        log "RERUN: main has new commits since last run (merge detected) — clearing marker"
        rm -f "$MARKER"
    else
        log "SKIP: Pipeline already ran today ($TODAY)"
        exit 0
    fi
fi

# Only run between 6 AM and 11 PM (wide window for post-merge reruns)
HOUR=$(date +%H)
if [ "$HOUR" -lt 6 ] || [ "$HOUR" -ge 23 ]; then
    log "SKIP: Outside run window (hour=$HOUR, allowed=06-22)"
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

/opt/homebrew/bin/python3 run.py "$@"
EXIT_CODE=$?

# Mark today as done only on success — failures can be retried by the 30-min interval
if [ "$EXIT_CODE" -eq 0 ]; then
    # Store the commit hash we ran against so we can detect new merges
    git rev-parse HEAD > "$MARKER" 2>/dev/null || touch "$MARKER"
else
    log "WARN: Pipeline failed (exit=$EXIT_CODE) — marker NOT set, will retry next trigger"
    # Log crash to shared issue log so the harness knows about it
    CRASH_LINE=$(grep -m1 "ERROR\|Traceback\|Error:" reports/launchd-stderr.log 2>/dev/null | tail -1 || echo "unknown error")
    /opt/homebrew/bin/python3 -m harness.issues log "pipeline" "Pipeline crashed (exit=$EXIT_CODE)" "$CRASH_LINE" 2>/dev/null || true
fi

# Clean up
rm -f "$LOCK"
rmdir "$LOCK_DIR" 2>/dev/null
kill "$CAFF_PID" 2>/dev/null

log "DONE: Pipeline finished with exit code $EXIT_CODE"
exit $EXIT_CODE
