# slack_bot/

> Socket Mode daemon with channel-based handler pattern.

## What It Does

Listens for Slack events via Socket Mode. Routes messages to handlers based on channel. Handlers dispatched in **daemon threads** so slow handlers (skills pipeline: 2-5 min) don't block other channels.

## Key Files

- `bot.py` — SocketModeClient setup, event routing, threaded dispatch
- `handlers/base.py` — BaseHandler with `read_url()` (Jina Reader + direct fallback), `reply()`, `react()`
- `handlers/posts.py` — #mp-posts: URL → article → Creative Director → writers → critics → humanizer → expeditor
- `handlers/skills.py` — #mp-skills: skill tip → Bluesky + LinkedIn drafts → humanizer → approval
- `registry.py` — Channel ID → handler class mapping (Keychain or env vars)

## URL Reading (`base.py`)

`read_url()` uses Jina Reader (`r.jina.ai`) with a direct-curl fallback:
1. Try Jina Reader first
2. Detect Jina error responses (JSON with `code >= 400`) — these are NOT content
3. Fall back to direct fetch with browser User-Agent + HTML stripping

**Known issue (fixed 2026-04-02):** Jina errors (like 451 SecurityCompromiseError) were passed through as article content because curl exits 0 even when Jina returns an error JSON. Pipeline would feed error JSON to writers, producing empty drafts.

## Handler Dispatch (`bot.py`)

Handlers run in daemon threads via `threading.Thread`. This prevents a slow handler (e.g., skills running 4x `claude -p` calls) from blocking event processing for other channels.

## Depends On

slack_sdk (WebClient, SocketModeClient). `orchestrator/agents.py` for `run_claude_prompt()`. `social/posting.py` for platform clients.

## Last Modified

2026-04-02 — Jina error detection, direct URL fallback, threaded dispatch, skills silent-ignore fix.
