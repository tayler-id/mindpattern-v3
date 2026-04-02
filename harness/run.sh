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
cd /Users/taylerramsay/Projects/mindpattern-v3
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

# ── Daily health report ───────────────────────────────────────────

log "Posting daily health report..."
PYTHONPATH="$PROJECT_ROOT" "$VENV_PYTHON" -m harness.health_report --slack >> "$LOGFILE" 2>&1 || log "WARN: Health report failed"

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

    # ── Fix Agent (deterministic worktree) ──────────────────────────
    local FIX_BRANCH="harness/${TICKET_ID}"
    local FIX_WORKTREE="$PROJECT_ROOT/.harness-worktrees/${TICKET_ID}"
    mkdir -p "$PROJECT_ROOT/.harness-worktrees"

    git worktree remove "$FIX_WORKTREE" --force 2>/dev/null || true
    git branch -D "$FIX_BRANCH" 2>/dev/null || true
    git worktree add -b "$FIX_BRANCH" "$FIX_WORKTREE" main 2>/dev/null
    if [ ! -d "$FIX_WORKTREE" ]; then
        log "[slot $SLOT] FAIL: Could not create worktree for $TICKET_ID"
        python3 -m harness.tickets mark-failed "$TICKET" "Worktree creation failed"
        return 1
    fi

    # Knowledge summary goes into --append-system-prompt so the Anthropic API
    # caches it across parallel fix agents (agents 2 and 3 get cache hits).
    # Only the per-ticket user prompt changes between agents.
    local KNOWLEDGE_SUMMARY
    KNOWLEDGE_SUMMARY=$(python3 -m harness.knowledge_graph summary 2>/dev/null | head -300 || true)

    claude -p "You are a TDD fix agent for the MindPattern project.
You are working in: $FIX_WORKTREE

TICKET:
$TICKET_CONTENT

INSTRUCTIONS:
1. You are already in worktree $FIX_WORKTREE on branch $FIX_BRANCH
2. FIRST: Read the SHARED ISSUE LOG in your system prompt. Print a one-line summary:
   KNOWLEDGE CHECK: Read N issues, relevant: <list any that relate to this ticket>
3. Read the files in files_to_modify
4. Write FAILING tests first in the tdd_spec.test_file
5. Implement the fix to make tests pass
6. Run: python3 -m pytest <test_file> -x -q
7. Update the knowledge graph:
   - Update harness/knowledge/<module>.md for any module you changed (behavior, API, known issues)
   - If you discovered a new failure pattern, add it to harness/knowledge/patterns-what-fails.md
   - If your fix involved a migration or schema change, document the migration pattern
8. If all tests pass, commit everything (including knowledge updates): git add -A && git commit -m \"fix: $TICKET_TITLE [harness/$TICKET_ID]\"
9. If tests fail after 3 tries, just stop.

IMPORTANT: All file paths are relative to $FIX_WORKTREE. Use cd $FIX_WORKTREE before any file operations." \
        --append-system-prompt "CODEBASE KNOWLEDGE (read this first, skip reading files already covered):

$KNOWLEDGE_SUMMARY" \
        --model "$(read_config fix model)" \
        --max-turns "$(read_config fix max_turns)" \
        --allowedTools "Bash Read Glob Grep Write Edit" \
        --disallowedTools "Skill Agent" \
        > "/tmp/harness-fix-${SLOT}.log" 2>&1 || true

    # Verify the agent acknowledged reading the knowledge graph
    local KG_CHECK
    KG_CHECK=$(grep -m1 "KNOWLEDGE CHECK:" "/tmp/harness-fix-${SLOT}.log" 2>/dev/null || echo "")
    if [ -n "$KG_CHECK" ]; then
        log "[slot $SLOT] $KG_CHECK"
    else
        log "[slot $SLOT] WARN: Fix agent did not confirm reading knowledge graph"
    fi

    log "[slot $SLOT] FIX DONE: worktree=$FIX_WORKTREE branch=$FIX_BRANCH"

    # ── Test (in worktree, no LLM) — only ticket's test file ──────
    local TEST_FILE
    TEST_FILE=$(python3 -c "import json; t=json.load(open('$TICKET')); print(t.get('tdd_spec',{}).get('test_file','tests/'))" 2>/dev/null) || TEST_FILE="tests/"

    local TEST_OUTPUT TEST_EXIT=0
    TEST_OUTPUT=$(cd "$FIX_WORKTREE" && python3 -m pytest "$TEST_FILE" -x -q --tb=short 2>&1) || TEST_EXIT=$?

    if [ $TEST_EXIT -ne 0 ]; then
        log "[slot $SLOT] FAIL: Tests failed for $TICKET_ID"
        python3 -m harness.tickets mark-failed "$TICKET" "Tests failed: ${TEST_OUTPUT:0:500}"
        python3 -m harness.issues log "harness/fix" "Ticket $TICKET_ID tests failed" "Ticket: $TICKET_TITLE. Test output: ${TEST_OUTPUT:0:300}" 2>/dev/null || true
        git worktree remove "$FIX_WORKTREE" --force 2>/dev/null || true
        return 1
    fi
    log "[slot $SLOT] TESTS PASSED"

    # ── Review Agent (no worktree — read-only) ────────────────────
    (cd "$FIX_WORKTREE" && git push origin "$FIX_BRANCH" 2>/dev/null) || true

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
        > "/tmp/harness-review-${SLOT}.log" 2>&1 || true

    # Check if PR was created
    local PR_URL
    PR_URL=$(grep -o 'https://github.com/[^ ]*pull/[0-9]*' "/tmp/harness-review-${SLOT}.log" 2>/dev/null | head -1 || true)

    if [ -n "$PR_URL" ]; then
        log "[slot $SLOT] PR: $PR_URL"
        python3 -m harness.tickets mark-done "$TICKET" "$PR_URL"
        slack_notify "✅ *PR Ready* [\`$TICKET_ID\`] $TICKET_TITLE\n$PR_URL"
    else
        if grep -q "REJECTED" "/tmp/harness-review-${SLOT}.log" 2>/dev/null; then
            local REASON
            REASON=$(grep -A3 "REJECTED" "/tmp/harness-review-${SLOT}.log" | head -3)
            log "[slot $SLOT] REJECTED: $TICKET_ID — $REASON"
            python3 -m harness.tickets mark-failed "$TICKET" "Review rejected: $REASON"
            python3 -m harness.issues log "harness/review" "Ticket $TICKET_ID rejected" "Ticket: $TICKET_TITLE. Reason: ${REASON:0:300}" 2>/dev/null || true
            slack_notify "❌ *Rejected* [\`$TICKET_ID\`] $TICKET_TITLE"
        else
            log "[slot $SLOT] NO PR: $TICKET_ID"
        fi
    fi

    git worktree remove "$FIX_WORKTREE" --force 2>/dev/null || true
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

# Check knowledge graph acknowledgment from scout
KG_CHECK=$(grep -m1 "KNOWLEDGE CHECK:" /tmp/harness-scout.log 2>/dev/null || echo "")
[ -n "$KG_CHECK" ] && log "  $KG_CHECK" || log "  WARN: Scout did not confirm reading knowledge graph"

OPEN_COUNT=$(python3 -m harness.tickets list open 2>/dev/null | wc -l | tr -d ' ')
log "Stage 1: Scout done. $OPEN_COUNT open tickets."

# ── Stage 1.5: Codex Adversarial Ticket Review ───────────────────

log "Stage 1.5: Codex adversarial review of new tickets..."
claude -p "$(cat harness/prompts/codex-ticket-review.md)" \
    --model "$(read_config scout model)" \
    --max-turns 15 \
    --allowedTools "Bash Read Glob Grep" \
    --disallowedTools "Write Edit Skill Agent" \
    > /tmp/harness-codex-review.log 2>&1 || log "WARN: Codex review exited with $?"

# Log verdicts
PASS_COUNT=$(grep -c "CODEX VERDICT:.*PASS" /tmp/harness-codex-review.log 2>/dev/null || echo 0)
REJECT_COUNT=$(grep -c "CODEX VERDICT:.*REJECT" /tmp/harness-codex-review.log 2>/dev/null || echo 0)
log "Stage 1.5: Codex review done. $PASS_COUNT passed, $REJECT_COUNT rejected."

# Check knowledge graph acknowledgment
KG_CHECK=$(grep -m1 "KNOWLEDGE CHECK:" /tmp/harness-codex-review.log 2>/dev/null || echo "")
[ -n "$KG_CHECK" ] && log "  $KG_CHECK" || log "  WARN: Codex agent did not confirm reading knowledge graph"

# Deterministically reject tickets that codex flagged
grep "CODEX VERDICT:.*REJECT" /tmp/harness-codex-review.log 2>/dev/null | while read -r line; do
    # Parse ticket ID from "CODEX VERDICT: 2026-04-01-005 — REJECT — reason"
    REJECT_ID=$(echo "$line" | sed -n 's/.*CODEX VERDICT: *\([^ ]*\).*/\1/p')
    REJECT_REASON=$(echo "$line" | sed -n 's/.*REJECT — *\(.*\)/\1/p')
    if [ -n "$REJECT_ID" ]; then
        REJECT_PATH=$(python3 -c "from harness.tickets import find_ticket_by_id; p=find_ticket_by_id('$REJECT_ID'); print(p if p else '')" 2>/dev/null)
        if [ -n "$REJECT_PATH" ]; then
            python3 -m harness.tickets mark-failed "$REJECT_PATH" "Codex adversarial: $REJECT_REASON"
            log "  REJECTED: $REJECT_ID — $REJECT_REASON"
        fi
    fi
    python3 -m harness.issues log "harness/codex" "Ticket $REJECT_ID rejected" "$REJECT_REASON" 2>/dev/null || true
done

OPEN_COUNT=$(python3 -m harness.tickets list open 2>/dev/null | wc -l | tr -d ' ')
log "Tickets after codex review: $OPEN_COUNT open."

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

    # Dispatch parallel (stagger 3s to avoid git lock race on worktree add)
    PIDS=()
    for i in "${!BATCH[@]}"; do
        [ "$i" -gt 0 ] && sleep 3
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
