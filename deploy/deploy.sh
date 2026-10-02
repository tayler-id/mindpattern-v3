#!/usr/bin/env bash
#
# Deploy the backend and hand the public site back warm.
#
# A Fly deploy replaces the machine, which empties every in-memory cache in
# dashboard/routes/api.py. A Vercel deploy drops the whole Next.js ISR cache.
# Either way the next reader pays the cold render, and on 2026-08-26 four
# deploys in one evening left mindpattern.ai cold with nothing to recover it.
# This script is the deploy: it ships, waits for the backend's own warm-up,
# then re-crawls the reader-facing paths. It exits nonzero if the crawl did
# not cover what it was asked to cover.
#
# The two cases need different path sets, so they get different scopes:
#   --scope changed  the day's published paths, purged then crawled. The
#                    default after a backend deploy.
#   --scope site     every path in sitemap.xml, crawled without a purge. The
#                    default for --warm-only, because a Vercel deploy has
#                    already dropped the entries a purge would drop.
#
# Usage:
#   deploy/deploy.sh                 # test, compile-gate, fly deploy, warm
#   deploy/deploy.sh --warm-only     # after a Vercel deploy: crawl the sitemap
#   deploy/deploy.sh --skip-tests    # gate on py_compile only (rare)
#
set -euo pipefail

APP="mindpattern"
STRATEGY="immediate"
BACKEND_URL="https://mindpattern.fly.dev"
SITE_URL="https://mindpattern.ai"
DATE="$(date +%F)"
WAIT_MINUTES="10"
CRAWL_BUDGET_MINUTES="20"
RUN_DEPLOY=1
RUN_TESTS=1
SCOPE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --app) APP="$2"; shift 2 ;;
    --strategy) STRATEGY="$2"; shift 2 ;;
    --backend-url) BACKEND_URL="$2"; shift 2 ;;
    --site-url) SITE_URL="$2"; shift 2 ;;
    --date) DATE="$2"; shift 2 ;;
    --wait-minutes) WAIT_MINUTES="$2"; shift 2 ;;
    --crawl-budget-minutes) CRAWL_BUDGET_MINUTES="$2"; shift 2 ;;
    --scope) SCOPE="$2"; shift 2 ;;
    --warm-only|--skip-deploy) RUN_DEPLOY=0; shift ;;
    --skip-tests) RUN_TESTS=0; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# A warm-only run is the recovery after a Vercel deploy, which empties the
# whole ISR cache. Warming only the day's date-scoped paths would report
# "4 warmed, 0 failed" over ~780 story pages and 86 entity pages still cold.
if [ -z "$SCOPE" ]; then
  if [ "$RUN_DEPLOY" = "1" ]; then SCOPE="changed"; else SCOPE="site"; fi
fi

if [ "${MP_SANDBOX:-}" = "1" ]; then
  echo "MP_SANDBOX=1: refusing to deploy" >&2
  exit 3
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="$REPO_ROOT/.venv/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"

FLYCTL="$(command -v flyctl || true)"
[ -n "$FLYCTL" ] || FLYCTL="$HOME/.fly/bin/flyctl"

step() { printf '\n== %s\n' "$1"; }

# 1. Gates. Fly runs Python 3.11; the local venv is 3.14, so syntax that only
#    parses here would crash the machine on boot. Both gates are about what
#    gets shipped, so a warm-only run skips them: it ships nothing, and an
#    operator recovering the site should not be blocked by a missing 3.11.
if [ "$RUN_DEPLOY" = "1" ]; then
  step "compile gate (python3.11)"
  if ! command -v python3.11 >/dev/null; then
    echo "python3.11 not found; it is the gate for what Fly actually runs" >&2
    exit 4
  fi
  find dashboard orchestrator slack_bot social core memory policies agents \
    -name '*.py' -print0 2>/dev/null \
    | xargs -0 python3.11 -m py_compile
  echo "ok"

  if [ "$RUN_TESTS" = "1" ]; then
    step "tests"
    "$PY" -m pytest tests/ -q
  fi

  # 2. Ship.
  step "fly deploy ($APP, strategy=$STRATEGY)"
  "$FLYCTL" deploy -a "$APP" --strategy "$STRATEGY"
fi

# 3. Wait for the machine to answer, then for its cache warm-up to finish.
#    Crawling while the backend is still cold just times out at the edge.
step "waiting for $BACKEND_URL"
deadline=$(( $(date +%s) + WAIT_MINUTES * 60 ))
until curl -fsS --max-time 10 "$BACKEND_URL/healthz" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "healthz never came back within ${WAIT_MINUTES}m" >&2
    exit 5
  fi
  sleep 5
done
echo "healthz ok"

step "waiting for backend warm-up"
last=""
while :; do
  phase="$(curl -fsS --max-time 20 "$BACKEND_URL/api/warmup/status" 2>/dev/null \
    | "$PY" -c 'import json,sys; print((json.load(sys.stdin) or {}).get("phase","unknown"))' \
    2>/dev/null || echo unreachable)"
  if [ "$phase" != "$last" ]; then
    echo "phase: $phase"
    last="$phase"
  fi
  case "$phase" in
    done) break ;;
    failed|cancelled)
      echo "backend warm-up ended as '$phase'; warming the site anyway" >&2
      break ;;
  esac
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "backend warm-up still '$phase' after ${WAIT_MINUTES}m; warming anyway" >&2
    break
  fi
  sleep 10
done

# The warm-up keeps phase 'done' even when steps were abandoned, because
# orchestrator/sync.py and the loop above branch on that vocabulary. `incomplete`
# is the only field that names the gaps, so print it here rather than let a
# deploy read as clean over an entity step that warmed nothing.
incomplete="$(curl -fsS --max-time 20 "$BACKEND_URL/api/warmup/status" 2>/dev/null \
  | "$PY" -c 'import json,sys; print(",".join((json.load(sys.stdin) or {}).get("incomplete") or []))' \
  2>/dev/null || echo "")"
if [ -n "$incomplete" ]; then
  echo "backend warm-up finished with gaps in: $incomplete" >&2
fi

# 4. Re-crawl the reader paths (purging first, when the scope calls for it).
#    Nonzero here fails the deploy: a cold site is not a finished deploy.
step "warm $SITE_URL (scope=$SCOPE)"
"$PY" -m orchestrator.sync warm \
  --date "$DATE" \
  --site-url "$SITE_URL" \
  --backend-url "$BACKEND_URL" \
  --backend-wait-minutes 2 \
  --scope "$SCOPE" \
  --crawl-budget-minutes "$CRAWL_BUDGET_MINUTES"

echo
if [ "$RUN_DEPLOY" = "1" ]; then
  echo "deploy complete: $APP shipped, $SITE_URL warmed (scope=$SCOPE)"
else
  echo "warm complete: $SITE_URL warmed (scope=$SCOPE)"
fi
