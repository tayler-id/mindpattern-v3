#!/bin/bash
# MindPattern project statusline
PROJECT_DIR="/Users/taylerramsay/Projects/mindpattern-v3"
DB="$PROJECT_DIR/data/ramsay/traces.db"
TICKETS_DIR="$PROJECT_DIR/harness/tickets"

# Git branch
branch=$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")

# Last pipeline run
if [ -f "$DB" ]; then
  run=$(sqlite3 "$DB" "SELECT status, completed_at FROM pipeline_runs ORDER BY started_at DESC LIMIT 1;" 2>/dev/null)
  if [ -n "$run" ]; then
    status=$(echo "$run" | cut -d'|' -f1)
    completed=$(echo "$run" | cut -d'|' -f2)
    # Extract date portion only
    run_date=$(echo "$completed" | cut -dT -f1 | cut -c6-)
    if [ "$status" = "completed" ]; then
      pipeline="ok $run_date"
    else
      pipeline="$status $run_date"
    fi
  else
    pipeline="no runs"
  fi
else
  pipeline="no db"
fi

# Open harness tickets (status: "open" or "in_progress" in non-archived tickets)
if [ -d "$TICKETS_DIR" ]; then
  open_count=$(grep -rl '"status":\s*"open"' "$TICKETS_DIR"/*.json 2>/dev/null | wc -l | tr -d ' ')
  prog_count=$(grep -rl '"status":\s*"in_progress"' "$TICKETS_DIR"/*.json 2>/dev/null | wc -l | tr -d ' ')
  tickets="${open_count}open/${prog_count}wip"
else
  tickets="no tickets"
fi

echo "$branch | pipeline: $pipeline | tickets: $tickets"
