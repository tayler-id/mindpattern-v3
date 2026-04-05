#!/bin/bash
# MindPattern Autonomous Harness — parallel agent orchestrator.
#
# Scout finds issues → picks N tickets → dispatches parallel fix agents
# (each in its own worktree) → tests → review agents → PRs.
#
# PARALLEL_AGENTS=3 bash harness/run.sh     # 3 fix agents at once
# MAX_TICKETS=10 bash harness/run.sh        # up to 10 tickets per run
# MODE=single bash harness/run.sh           # one ticket only

set -euo pipefail
cd "$(dirname "$(realpath "$0")")/.."
PROJECT_ROOT="$(pwd)"

DATE=$(date +%Y-%m-%d)
LOCK="/tmp/mindpattern-harness.lock"
HOLD="/tmp/mindpattern-harness.hold"
PIPELINE_LOCK="/tmp/mindpattern-pipeline.lock.d"
LOGFILE="reports/harness-${DATE}.log"
PARALLEL_AGENTS="${PARALLEL_AGENTS:-3}"
MAX_TICKETS="${MAX_TICKETS:-10}"
MODE="${MODE:-continuous}"

mkdir -p reports

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOGFILE"
}

cleanup() {
    jobs -p 2>/dev/null | xargs kill 2>/dev/null || true
    wait 2>/dev/null || true
    rm -f "$LOCK"
    rmdir "${LOCK}.d" 2>/dev/null || true
    git worktree prune 2>/dev/null || true
    log "Cleanup complete"
}
trap cleanup EXIT

# ── Guards ─────────────────────────────────────────────────────────

[ -f "$HOLD" ] && { log "SKIP: On hold"; exit 0; }
[ -d "$PIPELINE_LOCK" ] && { log "SKIP: Pipeline running"; exit 0; }

if ! mkdir "${LOCK}.d" 2>/dev/null; then
    LOCK_PID=$(cat "$LOCK" 2>/dev/null || true)
    if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
        log "SKIP: Already running (pid=$LOCK_PID)"; exit 0
    fi
    rm -f "$LOCK"; rmdir "${LOCK}.d" 2>/dev/null || true
    mkdir "${LOCK}.d" 2>/dev/null || exit 0
fi
echo "$$" > "$LOCK"

# Pull latest main before running
BRANCH=$(git branch --show-current 2>/dev/null)
if [ "$BRANCH" = "main" ]; then
    log "Pulling latest main..."
    git pull origin main --ff-only >> "$LOGFILE" 2>&1 || log "WARN: git pull failed"
fi

log "=== Harness started | parallel=$PARALLEL_AGENTS max=$MAX_TICKETS mode=$MODE ==="

# ── Helpers ────────────────────────────────────────────────────────

read_config() {
    python3 -c "import json; c=json.load(open('harness/config.json')); print(c['stages']['$1']['$2'])"
}

VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python3"
[ ! -x "$VENV_PYTHON" ] && VENV_PYTHON="python3"

slack_notify() {
    local MSG="$1"
    PYTHONPATH="$PROJECT_ROOT" "$VENV_PYTHON" -c "
import json, subprocess
try:
    tok = subprocess.run(['security','find-generic-password','-s','slack-bot-token','-a','mindpattern','-w'],
        capture_output=True,text=True,timeout=10).stdout.strip()
    cfg = json.loads(subprocess.run(['security','find-generic-password','-s','slack-channel-config','-a','mindpattern','-w'],
        capture_output=True,text=True,timeout=10).stdout.strip())
    ch = cfg.get('harness','')
    if tok and ch:
        from slack_sdk import WebClient
        WebClient(token=tok).chat_postMessage(channel=ch, text='''$MSG''')
except: pass
" 2>/dev/null || true
}

slack_post_backlog() {
    PYTHONPATH="$PROJECT_ROOT" "$VENV_PYTHON" -c "
import json, subprocess, sys
sys.path.insert(0, '$PROJECT_ROOT')
from slack_sdk import WebClient
from harness.tickets import list_tickets

tok = subprocess.run(['security','find-generic-password','-s','slack-bot-token','-a','mindpattern','-w'],
    capture_output=True,text=True,timeout=10).stdout.strip()
cfg = json.loads(subprocess.run(['security','find-generic-password','-s','slack-channel-config','-a','mindpattern','-w'],
    capture_output=True,text=True,timeout=10).stdout.strip())
ch = cfg.get('harness','')

tickets = list_tickets(status='open')
msg = ':mag: *Harness Backlog — {} open tickets*\n\n'.format(len(tickets))
for t in sorted(tickets, key=lambda x: (x.get('priority','P3'), x.get('created_at',''))):
    prio = t.get('priority','?')
    emoji = ':red_circle:' if prio == 'P1' else (':large_orange_circle:' if prio == 'P2' else ':white_circle:')
    msg += '{} \`[{}]\` \`{}\` — {}\n'.format(emoji, prio, t.get('id','?'), t.get('title','?'))
msg += '\n_Fix agents dispatching next._'

WebClient(token=tok).chat_postMessage(channel=ch, text=msg)
" 2>/dev/null || true
}

# Find the newest worktree that was created after a given timestamp
find_newest_worktree() {
    local AFTER_TS="$1"
    local WT_DIR="$PROJECT_ROOT/.claude/worktrees"
    [ ! -d "$WT_DIR" ] && return

    for d in $(ls -t "$WT_DIR" 2>/dev/null); do
        local FULL="$WT_DIR/$d"
        if [ -d "$FULL/.git" ] || [ -f "$FULL/.git" ]; then
            # Check if created after our timestamp
            local DIR_TS
            DIR_TS=$(stat -f %m "$FULL" 2>/dev/null || stat -c %Y "$FULL" 2>/dev/null || echo 0)
            if [ "$DIR_TS" -ge "$AFTER_TS" ]; then
                echo "$FULL"
                return
            fi
        fi
    done
}

# ── Process one ticket: fix → test → review ────────────────────────

process_ticket() {
    local TICKET="$1"
    local SLOT="$2"

    local TICKET_ID TICKET_TITLE TICKET_CONTENT
    TICKET_ID=$(python3 -c "import json; print(json.load(open('$TICKET'))['id'])")
    TICKET_TITLE=$(python3 -c "import json; print(json.load(open('$TICKET'))['title'])")
    TICKET_CONTENT=$(cat "$TICKET")

    log "[slot $SLOT] START: $TICKET_ID — $TICKET_TITLE"

    # ── Pre-fix gates (deterministic, no LLM) ────────────────────
    local PRE_GATE_RESULT PRE_GATE_EXIT=0
    PRE_GATE_RESULT=$(PYTHONPATH="$PROJECT_ROOT" "$VENV_PYTHON" -m harness.gates pre-fix "$TICKET" 2>&1) || PRE_GATE_EXIT=$?
    if [ $PRE_GATE_EXIT -ne 0 ]; then
        log "[slot $SLOT] GATE FAIL (pre-fix): $TICKET_ID — $PRE_GATE_RESULT"
        python3 -m harness.tickets mark-failed "$TICKET" "Pre-fix gate failed: ${PRE_GATE_RESULT:0:300}"
        return 1
    fi
    log "[slot $SLOT] PRE-FIX GATES PASSED"

    # ── Fix Agent (worktree) ──────────────────────────────────────
    local BEFORE_TS
    BEFORE_TS=$(date +%s)

    claude -p "You are a TDD fix agent for the MindPattern project.

TICKET:
$TICKET_CONTENT

INSTRUCTIONS:
1. Read the files in files_to_modify
2. Write FAILING tests first in the tdd_spec.test_file
3. Implement the fix to make tests pass
4. Run: python3 -m pytest <test_file> -x -q
5. If all pass, commit: git add -A && git commit -m \"fix: $TICKET_TITLE [harness/$TICKET_ID]\"
6. If tests fail after 3 tries, just stop." \
        --model "$(read_config fix model)" \
        --max-turns "$(read_config fix max_turns)" \
        --allowedTools "Bash Read Glob Grep Write Edit" \
        --disallowedTools "Skill Agent" \
        -w \
        > "/tmp/harness-fix-${SLOT}.log" 2>&1 || true

    # Find the worktree that was just created
    local FIX_WORKTREE FIX_BRANCH
    FIX_WORKTREE=$(find_newest_worktree "$BEFORE_TS")

    if [ -z "$FIX_WORKTREE" ] || [ ! -d "$FIX_WORKTREE" ]; then
        log "[slot $SLOT] FAIL: No worktree created for $TICKET_ID"
        python3 -m harness.tickets mark-failed "$TICKET" "Fix agent produced no worktree"
        return 1
    fi

    FIX_BRANCH=$(cd "$FIX_WORKTREE" && git branch --show-current 2>/dev/null || true)
    log "[slot $SLOT] FIX DONE: worktree=$FIX_WORKTREE branch=$FIX_BRANCH"

    # ── Test (in worktree, no LLM) ────────────────────────────────
    local TEST_OUTPUT TEST_EXIT=0
    TEST_OUTPUT=$(cd "$FIX_WORKTREE" && python3 -m pytest tests/ -x -q --tb=short 2>&1) || TEST_EXIT=$?

    if [ $TEST_EXIT -ne 0 ]; then
        log "[slot $SLOT] FAIL: Tests failed for $TICKET_ID"
        python3 -m harness.tickets mark-failed "$TICKET" "Tests failed: ${TEST_OUTPUT:0:500}"
        return 1
    fi
    log "[slot $SLOT] TESTS PASSED"

    # ── Post-fix gates (deterministic, no LLM) ───────────────────
    local CHANGED_FILES POST_GATE_RESULT POST_GATE_EXIT=0
    CHANGED_FILES=$(cd "$FIX_WORKTREE" && git diff main --name-only 2>/dev/null | tr '\n' ' ')
    POST_GATE_RESULT=$(PYTHONPATH="$PROJECT_ROOT" "$VENV_PYTHON" -m harness.gates post-fix "$TICKET" "$FIX_BRANCH" $CHANGED_FILES 2>&1) || POST_GATE_EXIT=$?
    if [ $POST_GATE_EXIT -ne 0 ]; then
        log "[slot $SLOT] GATE FAIL (post-fix): $TICKET_ID — $POST_GATE_RESULT"
        python3 -m harness.tickets mark-failed "$TICKET" "Post-fix gate failed: ${POST_GATE_RESULT:0:300}"
        return 1
    fi
    log "[slot $SLOT] POST-FIX GATES PASSED"

    # ── Review Agent (separate worktree) ──────────────────────────
    # Push the fix branch first so the reviewer can see it
    (cd "$FIX_WORKTREE" && git push origin "$FIX_BRANCH" 2>/dev/null) || true

    local REVIEW_BEFORE_TS
    REVIEW_BEFORE_TS=$(date +%s)

    claude -p "You are a code review agent for MindPattern.

TICKET:
$TICKET_CONTENT

The fix is on branch: $FIX_BRANCH

INSTRUCTIONS:
1. Run: git fetch origin && git diff main...$FIX_BRANCH --stat && git diff main...$FIX_BRANCH
2. Check: changes match ticket requirements, tests are meaningful, no regressions
3. If good: gh pr create --base main --head $FIX_BRANCH --title \"$TICKET_TITLE\" --body \"Harness ticket $TICKET_ID. $(echo "$TICKET_CONTENT" | python3 -c "import sys,json; t=json.load(sys.stdin); print(' '.join(t.get('requirements',[])))") \"
4. If bad: print REVIEW: REJECTED and explain why" \
        --model "$(read_config review model)" \
        --max-turns "$(read_config review max_turns)" \
        --allowedTools "Bash Read Glob Grep" \
        --disallowedTools "Write Edit Skill Agent" \
        -w \
        > "/tmp/harness-review-${SLOT}.log" 2>&1 || true

    # Check if PR was created
    local PR_URL
    PR_URL=$(grep -o 'https://github.com/[^ ]*pull/[0-9]*' "/tmp/harness-review-${SLOT}.log" 2>/dev/null | head -1 || true)

    if [ -n "$PR_URL" ]; then
        log "[slot $SLOT] PR: $PR_URL"
        python3 -m harness.tickets mark-done "$TICKET" "$PR_URL"
        # Record outcome so scout can learn from successes
        local PR_NUM
        PR_NUM=$(echo "$PR_URL" | grep -o '[0-9]*$')
        PYTHONPATH="$PROJECT_ROOT" "$VENV_PYTHON" -c "
from harness.tickets import record_pr_outcome
record_pr_outcome('$TICKET_ID', ${PR_NUM:-0}, 'pr_created', '$PR_URL')
" 2>/dev/null || true
        # Update knowledge graph
        PYTHONPATH="$PROJECT_ROOT" "$VENV_PYTHON" -c "
from harness.knowledge_graph import evolve
evolve('review_done', {'ticket_id': '$TICKET_ID', 'status': 'pr_created', 'pr_url': '$PR_URL'})
" 2>/dev/null || true
        slack_notify "✅ *PR Ready* [\`$TICKET_ID\`] $TICKET_TITLE\n$PR_URL"
    else
        if grep -q "REJECTED" "/tmp/harness-review-${SLOT}.log" 2>/dev/null; then
            local REASON
            REASON=$(grep -A3 "REJECTED" "/tmp/harness-review-${SLOT}.log" | head -3)
            log "[slot $SLOT] REJECTED: $TICKET_ID — $REASON"
            python3 -m harness.tickets mark-failed "$TICKET" "Review rejected: $REASON"
            # Record rejection so scout can learn from failures
            PYTHONPATH="$PROJECT_ROOT" "$VENV_PYTHON" -c "
from harness.tickets import record_pr_outcome
record_pr_outcome('$TICKET_ID', 0, 'rejected', close_reason=\"\"\"${REASON:0:200}\"\"\")
" 2>/dev/null || true
            # Update knowledge graph with failure pattern
            PYTHONPATH="$PROJECT_ROOT" "$VENV_PYTHON" -c "
from harness.knowledge_graph import evolve
evolve('review_done', {'ticket_id': '$TICKET_ID', 'status': 'rejected', 'reason': \"\"\"${REASON:0:200}\"\"\"})
" 2>/dev/null || true
            slack_notify "❌ *Rejected* [\`$TICKET_ID\`] $TICKET_TITLE"
        else
            log "[slot $SLOT] NO PR: $TICKET_ID — marking failed"
            python3 -m harness.tickets mark-failed "$TICKET" "Review produced no PR and no rejection"
        fi
    fi

    # Clean up review worktree (fix worktree stays for the branch)
    local REVIEW_WT
    REVIEW_WT=$(find_newest_worktree "$REVIEW_BEFORE_TS")
    [ -n "$REVIEW_WT" ] && git worktree remove "$REVIEW_WT" --force 2>/dev/null || true
}

# ── Stage 1: Scout ─────────────────────────────────────────────────

log "Stage 1: Scout scanning for issues..."
python3 -m harness.tickets decay 2>/dev/null || true

claude -p "$(cat harness/prompts/scout.md)" \
    --model "$(read_config scout model)" \
    --max-turns 15 \
    --allowedTools "Bash Read Glob Grep Write" \
    --disallowedTools "Skill Agent" \
    > /tmp/harness-scout.log 2>&1 || log "WARN: Scout exited with $?"

OPEN_COUNT=$(python3 -m harness.tickets list open 2>/dev/null | wc -l | tr -d ' ')
log "Stage 1: Scout done. $OPEN_COUNT open tickets."

# ── Stage 2: Research ──────────────────────────────────────────────

log "Stage 2: Research scanning for ideas..."
claude -p "$(cat harness/prompts/research.md)" \
    --model "$(read_config research model)" \
    --max-turns 15 \
    --allowedTools "Bash Read Glob Grep Write WebSearch WebFetch Agent" \
    --disallowedTools "Skill" \
    > /tmp/harness-research.log 2>&1 || log "WARN: Research exited with $?"

OPEN_COUNT=$(python3 -m harness.tickets list open 2>/dev/null | wc -l | tr -d ' ')
log "Tickets available: $OPEN_COUNT"
slack_post_backlog

# ── Stage 3: Parallel Fix/Test/Review ──────────────────────────────

TICKETS_DONE=0
ROUND=0

while [ "$TICKETS_DONE" -lt "$MAX_TICKETS" ]; do
    ROUND=$((ROUND + 1))
    [ -f "$HOLD" ] && { log "HOLD: Paused. $TICKETS_DONE done."; break; }

    # Collect batch
    BATCH=()
    for i in $(seq 1 "$PARALLEL_AGENTS"); do
        T=$(python3 -m harness.tickets pick 2>/dev/null) || true
        [ -z "$T" ] && break
        BATCH+=("$T")
        python3 -c "from harness.tickets import mark_in_progress; mark_in_progress('$T')"
    done

    [ ${#BATCH[@]} -eq 0 ] && { log "Queue empty. $TICKETS_DONE done."; break; }

    log "Round $ROUND: ${#BATCH[@]} parallel agents"
    slack_notify "🔧 *Round $ROUND* — dispatching ${#BATCH[@]} fix agents"

    # Dispatch parallel
    PIDS=()
    for i in "${!BATCH[@]}"; do
        process_ticket "${BATCH[$i]}" "$((i + 1))" &
        PIDS+=($!)
    done

    for PID in "${PIDS[@]}"; do wait "$PID" 2>/dev/null || true; done

    TICKETS_DONE=$((TICKETS_DONE + ${#BATCH[@]}))
    log "Round $ROUND done. $TICKETS_DONE total processed."

    [ "$MODE" = "single" ] && break
done

# ── Summary ────────────────────────────────────────────────────────

DONE=$(python3 -m harness.tickets list done 2>/dev/null | wc -l | tr -d ' ')
FAILED=$(python3 -m harness.tickets list failed 2>/dev/null | wc -l | tr -d ' ')
OPEN=$(python3 -m harness.tickets list open 2>/dev/null | wc -l | tr -d ' ')

log "=== HARNESS COMPLETE | processed=$TICKETS_DONE PRs=$DONE failed=$FAILED remaining=$OPEN ==="
slack_notify "📊 *Harness Run Complete*\nProcessed: $TICKETS_DONE\nPRs created: $DONE\nFailed: $FAILED\nRemaining: $OPEN"
