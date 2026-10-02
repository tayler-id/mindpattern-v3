# Spec: model routing, a two-CLI harness, and policy files

**Date:** 2026-10-02 · **Status:** decisions recorded 2026-10-02, ready to build · **Branch:** `fix/restore-learning-loops` (uncommitted work present)

Each phase below ends in a review.

## Decisions (Tayler, 2026-10-02)

| Question | Decision |
|---|---|
| Claude usage budget | Allowed to rise for deeper research. Usage is recorded and a soft per-run ceiling alerts (D7). |
| Email timing | A later email is fine. The deep-dive pass (D4 R4) is approved. |
| `model_calls` table | Approved. |
| Run tracing | Required. Store every agent run, including subagents, so any run can be traced and inspected (D7). |
| Sol model | GPT-6.1 Sol. Codex already defaults to `gpt-6.1-sol` with `model_reasoning_effort = "xhigh"` in `~/.codex/config.toml`. The harness passes the model and the effort per task. |
| Fable 5.1 for story selection | Open. |
| Branch | Open. Work happens in a separate git worktree either way (see Rollout safety). |

## Rollout safety

launchd runs the pipeline from the live checkout at `~/Projects/mindpattern-v3` every morning, and `run-launchd.sh` pulls only on `main`. Half-finished code in that checkout would run at 08:00 the next day. So every phase is built and tested in a separate git worktree, and reaches the live checkout only after it passes its phase check. The verification toolkit and the launcher gate, still uncommitted in the live checkout, stay untouched.

## Objective

Make the daily newsletter and the Rabbit Hole stories better while Claude plan usage stays flat or drops. Tayler asked for these on 2026-10-02:

1. Opus 5.5 writes the newsletter and makes the editorial decisions, starting with which stories to write.
2. Sonnet 5.5 does research and the site stories, to save usage.
3. GPT-6.1 Sol, through the Codex CLI, joins the flow because it is cheap, strong, and billed to a separate plan.
4. Research goes deeper every day, because better stories need more evidence.
5. The writing reads as human. The tells that mark Claude prose come out.
6. Models, policies, and output contracts live in files that can change without code edits.
7. Nothing breaks the daily run while this lands.

Python keeps owning control flow. No model chooses the next step, and that rule does not change here.

## Assumptions

Correct any of these before Phase 1 starts.

1. Sol is OpenAI's GPT-6.1 Sol, model string `gpt-6.1-sol`, called through the Codex CLI (`codex-cli 0.156.1`) and billed to Tayler's Codex plan. Confirmed 2026-10-02.
2. Both CLIs stay subscription-backed. No API keys are added to the project.
3. "Stripe Python workflow" was a voice-typing slip for "straight up Python", the pipeline itself. Confirmed 2026-10-02.
4. Social and engagement stay off on scheduled runs.
5. Claude usage may rise for deeper research. Codex usage is extra, on its own plan. Both are recorded per call.
6. The deep-dive pass (D4 R4) adds a pipeline phase and moves the email later. Approved 2026-10-02.

## Baseline: what the Oct 1 run actually used

Generated with `tools/usage_report.py --date 2026-10-01` (Phase 0, built and tested 2026-10-02), which reads the Claude session transcripts the run left in `~/.claude/projects/-Users-taylerramsay-Projects-mindpattern-v3/`. The pipeline itself records zero tokens today (B5). Dollar figures use Anthropic API list prices from `config/pricing.json`. The subscription does not charge them, but plan limits track them roughly.

An earlier hand count in this spec gave 3.4M output tokens and about $128. It was wrong. A transcript writes one API response as several lines that repeat its usage, and the hand count summed lines (1,582) instead of responses (634). The script dedupes by response ID, and a test fails if that dedupe is removed.

| Task | Model | Sessions | Responses | Output tokens | Cached reads | API-price equivalent |
|---|---|---|---|---|---|---|
| Research agents | Opus 5.5 | 15 | 432 | 482,511 | 52,589,836 | $32.72 |
| Site story writer | Sonnet 5 | 71 | 108 | 456,553 | 3,756,420 | $10.88 |
| Site story critic | Sonnet 5 | 49 | 49 | 415,653 | 1,211,075 | $6.11 |
| Knowledge flush hook (B4) | Sonnet 4.6 | 33 | 33 | 13,139 | 572,561 | $1.84 |
| Newsletter writer | Opus 5 | 1 | 1 | 31,605 | 7,529 | $1.52 |
| KG extraction | Haiku 4.5 | 8 | 8 | 155,659 | 114,528 | $0.94 |
| Story selection | Opus 5 | 1 | 1 | 6,959 | 0 | $0.82 |
| Identity and learnings | Sonnet 5.5 | 2 | 2 | 2,538 | 0 | $0.18 |
| **Total** | | **180** | **634** | **1,564,617** | **58,251,949** | **$55.01** |

Other days from the same script: Sep 27 $61.31, Sep 30 $66.07, Oct 2 $37.84 (the run was still going).

List prices per million tokens (Anthropic model reference, cached 2026-09-25):

| Model | New input | Output | Cached read |
|---|---|---|---|
| Opus 5.5 `claude-opus-5-5` | $4 | $20 | $0.20 |
| Opus 5 `claude-opus-5` | $5 | $25 | |
| Sonnet 5.5 `claude-sonnet-5-5` | $2 | $10 | $0.20 |
| Haiku 4.5 `claude-haiku-4-5` | $1 | $5 | |

### Findings

- **B1. Research is about 60% of the cost, and most of its input is re-reading.** The 15 research sessions read 52.6M cached tokens and wrote 2.5M new tokens into the cache. Each agent makes 30 to 83 tool calls, 752 in all on Oct 1 (372 Bash, 218 WebFetch, 162 WebSearch). Every fetched page is written into the cache once and then re-read on every later turn.
- **B2. Why Sonnet 5.5 does not halve research cost.** Sonnet 5.5 is half the price of Opus 5.5 for new input, cache writes, and output. Cached reads cost $0.20 per million on both. Research on Oct 1 cost $12.54 in cache writes, $10.52 in cached reads, and $9.65 in output. On Sonnet 5.5 that becomes about $6.27, $10.52, and $4.83, so about $21.60 instead of $32.72, a cut of about a third. Writing jobs are mostly output, so they get the full half-price cut. Smaller fetched pages (D4 R2) cut both the writes and the re-reads, on any model.
- **B2a. The newsletter is the cheapest part of the day.** Story selection plus writing cost $2.34 (4%). Site stories cost $16.99 (31%). Spending more on the newsletter's model buys quality cheaply.
- **B3. Agents that hit the turn cap lose everything.** "Error: Reached max turns (35)" means the agent spent its whole budget and printed no JSON. It hit 4 of 13 agents on Sep 29 and 6 of 13 on Sep 27.
- **B4. Hooks fire on pipeline calls.** `.claude/settings.json` runs `hooks/session_end.py` (which spawns `knowledge/flush.py`, a Sonnet 4.6 call) and `hooks/session_start.py` (which injects up to 20,000 characters of knowledge index) for every `claude -p` session. Both skip when `MINDPATTERN_AGENT` or `CLAUDE_INVOKED_BY` is set, but only research agents set it (`orchestrator/agents.py:_agent_env`). So the site writer, critic, synthesis, and KG calls each pay for an injected index and a summary call afterwards. Oct 1 had 33 of these summary sessions.
- **B5. No usage is recorded.** Every call uses `--output-format text`, so `traces.db agent_runs.input_tokens` and `output_tokens` are 0 for every row. A saving cannot be proven until this changes.
- **B6. Model choices are spread across seven places.** `orchestrator/router.py`, `orchestrator/site_writer.py` (`claude-sonnet-5`), `orchestrator/site_critic.py` (`claude-sonnet-5`), `kg/extract.py` (Haiku 4.5 default), `core/llm.py` (`claude-sonnet-4-6`), `knowledge/flush.py` (`claude-sonnet-4-6`), and environment overrides (`MP_SITE_STORY_WRITER_MODEL`, `MP_SITE_STORY_CRITIC_MODEL`, `MP_KG_MODEL`).
- **B7. The newsletter runs on an older, pricier model.** `router.py` pins both synthesis passes to `claude-opus-5[1m]`, while research uses the `opus` alias, which now resolves to Opus 5.5.
- **B8. The research prompt still tells agents to spawn subagents** (`orchestrator/agents.py`, "Subagent Delegation" block). None did on Oct 1. The text is dead weight in every agent prompt.
- **B9. Site stories take about 5 model calls each.** The loop is write, lint, critique, revise, critique (`orchestrator/site_critic.py:write_story_with_review`). Critics often flag fabrication (score 0), meaning the writer adds claims the evidence pack does not support. Thin evidence causes some of that (D4 R4).

## Design

### D0. Code first: a model only does judgment and prose

Tayler's rule (2026-10-02): a model is called only where judgment or prose is needed. Everything code can do is a script or CLI with `--help`, JSON output, and tests. That covers fetching, cleaning, counting, deduping, validating, formatting, storing, and checking. A rule code can enforce never lives only in a prompt. When a prompt and code both state a rule, the code is the source and the prompt text is generated from the policy file.

Each step, today and after:

| Step | Today | After |
|---|---|---|
| Preflight, trend scan | Code | Code (unchanged) |
| Research | The agent searches, reads whole pages into context, and prints one JSON blob at the end. Python validates afterwards. | The agent decides what to look at. It fetches, checks, and stores through the `mp` CLI below, which validates every finding as it is added. |
| Finding checks (fields, age, banned entities, injection, duplicates) | Policy engine after the agent exits | `mp finding add` at write time, so the agent sees the rejection and its reason immediately. The policy engine still runs as a second check. |
| Story selection | Opus, plus a code repeat check | Same, with the selection contract enforced by schema |
| Deep-dive evidence | none | The agent finds sources. `mp evidence add` validates and assembles the pack. |
| Newsletter writing | Opus, then code (headline, prose gate, URL check) | Same, plus the contract and the policy-driven lint |
| Sol editing | none | Sol returns an edit list. Code applies edits that keep facts, numbers, and links. |
| Site story writing | Sonnet, then code lint | The writer runs `mp lint` on its draft before it answers. Mechanical problems never reach the critic. |
| Site story critic | Sonnet judges everything | Sol judges taste and grounding only |
| KG extraction | Haiku, then code resolution | Same |
| Usage, tracing, budget, retention | none | Code (D7) |
| Knowledge flush on pipeline calls | Sonnet 4.6 summary per session | Removed (B4) |

**CLIs and scripts to build.** Each is a Python module with tests, JSON output, and exit codes that mean something.

| Command | Used by | What it does |
|---|---|---|
| `mp fetch <url> --max-chars N` | research and deep-dive agents | Readable text, capped, cached for the run, logged as a trace step. Replaces whole pages in agent context (R2). |
| `mp search "<query>" --source exa\|hn\|reddit\|web` | agents | Normalized results from the existing source modules |
| `mp seen "<url or title>"` | agents | Checks the 180-day history and today's other agents before the agent writes anything up |
| `mp finding add --json '{...}'` | research agents | Validates against `contracts/research_findings.schema.json` and `policies/research.json`, dedupes, appends to the run's findings file, prints accepted or rejected with the reason. Findings survive the turn cap (R1). |
| `mp findings list` | agents | What this agent has stored so far this run |
| `mp evidence add --story <id> --json '{...}'` | deep-dive agents | Validates and appends to the story's evidence pack |
| `mp lint <file> --policy writing` | writers, pipeline | Runs `policies/writing.json` over a draft. Same code the pipeline gate runs. |
| `mp tells --model M --since 30d` | Tayler, Phase 2 and 4 | Rate of each writing-policy pattern per 1,000 words in our own published text, against a human baseline corpus |
| `python -m core.config check` | INIT, Tayler | Validates `config/`, `policies/`, `contracts/`. A bad file stops the run before any model call. |
| `python -m orchestrator.trace ...` | Tayler | Runs, calls, subagents, steps, usage (D7) |
| `tools/usage_report.py --date D` | Tayler | Usage by task, model, and provider. Reads Claude transcripts until `model_calls` exists, then reads the table. |
| `tools/replay_day.py` | Tayler, bakeoffs | Reruns chosen stages of a past day into a scratch root (Phase 0) |
| `tools/bakeoff.py` | Tayler | Renders two versions of the same day side by side without labels and records the pick |

Agents get `mp` through a grant (`Bash(mp *)`), the same mechanism that grants `mcporter` and `twitter` today. `missing_granted_binaries()` already checks that a granted binary is installed. `mp` is free on this Mac (`which mp` finds nothing).

### D1. One harness for both CLIs

Python calls `claude` and `codex` directly, through one module, and records every call the same way. Claude does not call Codex. Routing Codex through a Claude session would spend Claude tokens to orchestrate it, hide Codex usage inside a Claude transcript, add a failure layer, and hand a control decision to a model.

New module `core/model_cli.py` replaces the six call sites in B6. `core/claude_cli.py:run_claude_process` stays as the process boundary, renamed `run_cli_process`, because its process-group kill and timeout handling already work.

```python
@dataclass(frozen=True)
class TaskRoute:
    """One row of config/models.json, validated at load."""
    task: str
    provider: Literal["claude", "codex"]
    model: str
    effort: str | None
    max_turns: int | None
    timeout_s: int
    fallback: "TaskRoute | None" = None


@dataclass(frozen=True)
class ModelResult:
    task: str
    provider: str
    model: str
    text: str
    parsed: dict | None          # set when the call had a contract
    outcome: str                 # success, max_turns, timeout, rate_limit, parse_error, other
    input_tokens: int
    output_tokens: int
    cached_read_tokens: int
    turns: int | None
    duration_ms: int


def call_model(task: str, prompt: str, *, contract: str | None = None,
               system_prompt_file: Path | None = None,
               tools: ToolGrant | None = None) -> ModelResult: ...
```

Provider argv:

- **claude:** `claude -p --model <m> --effort <e> --max-turns <n> --output-format json [--json-schema <contract>] [--append-system-prompt-file <f>] [--allowedTools ...] [--disallowedTools ...]`. The JSON result carries the text, the usage counts, the turn count, and an error subtype for max-turns.
- **codex:** `codex exec -m <m> --json --ephemeral --skip-git-repo-check -s read-only [--output-schema <contract>] -o <tmpfile> <prompt>`. The JSONL event stream carries token usage, and `-o` holds the final message.

Every call sets `CLAUDE_INVOKED_BY=mindpattern` and `MINDPATTERN_TASK=<task>` in its environment. That closes B4 without touching the hooks. Research agents keep `MINDPATTERN_AGENT` so the transcript hook still files their transcripts.

Every call writes one row to a new `traces.db` table `model_calls` (task, provider, model, outcome, token counts, turns, duration, run id). Approved 2026-10-02. D7 adds the steps table and the raw trace files, and replaces `--output-format json` with the stream format so the whole conversation is kept.

A route with a `fallback` retries once on the fallback provider when the first returns rate_limit, timeout, or a quota message. The site critic falls back from Sol to Sonnet 5.5, for example, so a Codex outage costs quality but not the day.

Phase 1 tests one hypothesis about the Automic Vault prompts. Each `claude -p` session runs `gh auth token`, and the vault asks Tayler to approve every one. If `--bare` or a pipeline-only setting stops that call, the harness uses it. If not, the fix stays a vault policy on Tayler's side.

### D2. Config files

```
config/
  models.json          task -> provider, model, effort, max_turns, timeout_s, fallback
policies/
  research.json        exists today; finding fields, age limit, injection patterns
  writing.json         new; mechanical writing rules (D3)
  editorial.json       new; story counts, caps, repeat checks
  social.json          exists today
contracts/
  research_findings.schema.json
  story_selection.schema.json
  site_story.schema.json
  critic_verdict.schema.json
  editor_edits.schema.json
```

JSON matches the existing `policies/*.json` files and needs no new dependency. One loader validates every file at the start of INIT and fails the run before any model call if a file is invalid. `orchestrator/prompt_tracker.py` already hashes prompt files each run. It extends to hash these files, so a quality change can be traced to a config or policy edit.

Proposed `config/models.json` after Phase 1 (Phase 1 first ships a table that reproduces today's models exactly, then flips them one task at a time):

```json
{
  "trend_scan":         {"provider": "claude", "model": "claude-haiku-4-5",  "timeout_s": 60},
  "research_agent":     {"provider": "claude", "model": "claude-sonnet-5-5", "effort": "medium", "max_turns": 35, "timeout_s": 1800},
  "story_selection":    {"provider": "claude", "model": "claude-opus-5-5",   "effort": "high",   "max_turns": 10, "timeout_s": 600},
  "story_deep_dive":    {"provider": "claude", "model": "claude-sonnet-5-5", "effort": "medium", "max_turns": 15, "timeout_s": 600},
  "newsletter_writer":  {"provider": "claude", "model": "claude-opus-5-5",   "effort": "high",   "max_turns": 30, "timeout_s": 900},
  "newsletter_editor":  {"provider": "codex",  "model": "gpt-6.1-sol",       "timeout_s": 600,  "enabled": false},
  "site_story_writer":  {"provider": "claude", "model": "claude-sonnet-5-5", "effort": "medium", "max_turns": 8,  "timeout_s": 300},
  "site_story_critic":  {"provider": "codex",  "model": "gpt-6.1-sol",       "timeout_s": 300,
                         "fallback": {"provider": "claude", "model": "claude-sonnet-5-5", "effort": "medium", "max_turns": 5, "timeout_s": 300}},
  "kg_extract":         {"provider": "claude", "model": "claude-haiku-4-5",  "max_turns": 1,  "timeout_s": 120}
}
```

The `gpt-6.1-sol` string is a placeholder until assumption 1 is confirmed. Whether the 5.5 models still need the `[1m]` suffix in the CLI gets checked in Phase 1, since the model reference lists 1M context as their default.

### D3. Policies and contracts

**Writing policy.** Mechanical writing rules live today in five places: `data/ramsay/mindpattern/voice.md`, `docs/specs/site-writer-rules.md`, `agents/references/ai-writing-patterns.md`, constants in `orchestrator/prose_gate.py`, and constants in `orchestrator/site_copy_lint.py`. The mechanical ones move into `policies/writing.json`:

- banned phrases and banned regex patterns, each with a reason
- budgets, such as the existing em-dash budget of six per issue
- protected spans (code, URLs, quotes) that checks skip
- structure rules (heading style, paragraph and sentence limits)
- the critic rubric, as text the critic prompt renders

`prose_gate.py`, `site_copy_lint.py`, the writer prompts, and the critic prompt all read this one file. Taste stays in `voice.md`, because code cannot check taste. The background research in `~/Documents/Research/2026-10-02-removing-ai-writing-tells.md` seeds the new rules.

**Editorial policy.** `policies/editorial.json` holds the newsletter story count (5 today), the site story cap (`MP_SITE_ISSUE_STORIES_MAX`, 20 today), the candidate-story count (the 5 extra stories a day the cap does not cover), and the repeat-check thresholds.

**Contracts.** Each model output that Python parses gets a JSON Schema file. The harness passes it to the CLI (`--json-schema` for Claude, `--output-schema` for Codex) and validates the result in Python again at the boundary. This replaces most of the hand-written recovery parsing (`_extract_balanced_json_blocks`, `core/llm.py:extract_json`) for calls that adopt a contract. Python validation stays even when the CLI enforces the schema.

### D4. Deeper research for the same usage

- **R1. Keep work when the turn cap hits.** Agents append findings to a file as they go (the `run_agent_with_files` pattern), so a cap keeps the findings gathered so far. The prompt also states the turn budget and asks for output with three turns left. Target: zero agents lost to the cap.
- **R2. Cut context growth.** Cap WebFetch reads per agent, prefer search snippets with targeted fetches, set effort to medium, delete the subagent block (B8), and trim the memory blocks in the prompt. Measure cached-read tokens per agent before and after.
- **R3. Move research to Sonnet 5.5, after a bakeoff.** Replay three past days with the same preflight data on Opus and on Sonnet. Compare findings that survive the four gates, and which version the selection pass prefers.
- **R4. Add a deep-dive pass.** After Opus picks the stories, one Sonnet agent per selected story finds the primary source, two corroborations, the numbers, and the strongest counterpoint, then writes an evidence pack to a contract. The newsletter writer and the site writer both get the richer pack, which should cut the critic's fabrication flags (B9). This adds a phase between story selection and newsletter writing, and it moves the email from about 30 minutes after start to about 45 to 50. Approved 2026-10-02.
- **R5. Sol as a research beat.** Later and optional. One extra Sol agent on its own plan could cover a beat or verify claims. It stays out of the first rollout.

### D5. Writing that reads as human

- **Newsletter.** Opus 5.5 writes. An optional Sol editor pass then returns a list of line edits, not a rewrite, scored against the writing policy rubric. Python applies an edit only if it keeps every number, URL, name, and quote. The deterministic prose gate runs last. A different model family is better at seeing Claude's habits than Claude is, and an edit list keeps facts out of its reach.
- **Site stories.** Sonnet 5.5 writes. Sol replaces Sonnet as the critic, with the existing one-revision loop. That moves about a quarter of Oct 1's Claude output onto the Codex plan.
- **Proof before switching.** A blind comparison on five past days of old against new output, picked by Tayler, plus the count of writing-policy violations per issue. Defaults switch only when the new version wins.

**What the October research changes** (`~/Documents/Research/2026-10-02-removing-ai-writing-tells.md`, 15 sources, read 2026-10-02):

- Tells are model-specific and drift between versions. One September 2026 study of 9 models found 65% of tells unique to one model family. So every rule in `policies/writing.json` records the model it targets, when it was measured, and a review-by date.
- The em dash stopped being a Claude tell with Opus 5.5. Opus 5.5's remaining tells are semantic ("this matters", "why X matters", "more than an X, it's a Y"), and the current word bank covers almost none of them. The budget stays as insurance.
- Measure our own tells. `mp tells --model M --since 30d` counts each policy pattern per 1,000 words in our own published issues, against a human baseline corpus, so the policy is tuned on MindPattern's output and not on someone else's list. The multipliers quoted in the research came through a summarizing fetch and get checked against the sources before any becomes a threshold.
- Sol has no published tell data yet, and neither does Sonnet 5.5. Both get measured before Phase 4 relies on them.
- Cross-family editing has a sound mechanism but no direct evidence. So Sol returns span-level findings, the original writer applies them, and the gates run again. Phase 4's blind comparison is the evidence.
- Each new writing rule ships with a failing fixture first, like every other guard here.

### D6. Free wins first

These need no bakeoff and land in Phase 1:

1. Set the environment marker on every pipeline call (B4).
2. Move the newsletter passes from Opus 5 to Opus 5.5 (B7).
3. Delete the subagent block from the research prompt (B8).
4. Record usage for every call (B5).
5. Fix the writer prompts that model the habits they ban. `agents/synthesis-writer.md:99-103` presents as "good" an exemplar with an em dash, a three-fragment opener, and an "uncomfortable truth:" reveal. `agents/references/ai-writing-patterns.md:21` and `:47` show fixes that invent first-person experience ("I've seen three teams at YC Demo Day", "My designer friends"), which teaches a factual newsletter to fabricate anecdotes. Verified 2026-10-02.
6. Make the newsletter word bank enforce, not just log. `orchestrator/runner.py:1997` records a prose-gate event only for replacements, length fixes, or budget overruns, so word-bank hits never block or repair anything. Verified 2026-10-02.

### D7. Run tracing: see what every agent did

Tayler can open any past run and see every model call in it: what each agent was asked, which provider and model ran it, every tool call it made and what came back, every subagent it started and what that subagent did, its final output, its tokens, its duration, and how it ended.

**Data shape.** Four levels, each linked to the one above:

| Level | Where | One per |
|---|---|---|
| Run | `traces.db pipeline_runs` (exists) | pipeline run |
| Call | `traces.db model_calls` (new) | CLI invocation, plus one per subagent inside it (`parent_call_id`) |
| Step | `traces.db model_call_steps` (new) | tool call: sequence, tool name, short input, ok or error, bytes returned |
| Raw | `data/ramsay/traces/<date>/<run_id>/<call_id>.events.jsonl.gz` and `.prompt.md.gz` | call: the complete event stream and the exact prompt |

`model_calls` also carries `phase`, `task`, `unit` (agent name or story slug, so a story's writer, critic, and revision calls group together), the config and prompt hashes, and the trace file path.

**Capture.** The harness reads each CLI's event stream, writes it to the gzipped file as it arrives, and builds the call and step rows when the call ends.

- Claude runs with `--output-format stream-json --verbose`. The stream carries the init event (model, tools), every assistant message and tool call, every tool result, subagent messages tagged with `parent_tool_use_id`, and the final result event with usage. The final text comes from the result event, so this replaces the `--output-format json` plan in D1.
- Codex runs with `--json`. Its JSONL events carry commands, messages, reasoning items, and per-turn usage.
- Both stream formats get pinned as recorded fixtures in `tests/fixtures/cli/`. A format change in a CLI update then fails a test, not a production run.

**Storage and retention.** About 65 MB of raw events a day, 19 MB gzipped (measured on the Oct 1 transcripts). `policies/observability.json` sets raw-file retention (default 90 days, about 1.7 GB) and keeps the index rows forever. The LEARN phase prunes old raw files. Traces hold fetched web pages and the identity files, so they stay on the Mac. They are never synced to Fly and never served publicly.

**Viewing.** A CLI first, then a private dashboard page that reads the same index.

```sh
.venv/bin/python3 -m orchestrator.trace runs --last 7            # runs with totals and outcomes
.venv/bin/python3 -m orchestrator.trace show <run_id>             # tree: phase, call, subagents, steps
.venv/bin/python3 -m orchestrator.trace call <call_id> --full     # prompt, each tool call and result, output
.venv/bin/python3 -m orchestrator.trace grep <run_id> "<text>"    # search tool inputs and results
.venv/bin/python3 -m orchestrator.trace usage --since 7d --by task,model
```

**Soft budget.** `policies/observability.json` sets a per-run ceiling in output tokens and API-price equivalent. LEARN compares the run against it and alerts Slack when it is over. It never blocks a run.

**What it replaces.** `hooks/session-transcript.py` files research transcripts into the vault today. Once D7 captures every call, that hook goes. The dashboard's `agent_runs` readers move to `model_calls`, then the `agent_runs` writers go, so `traces.db` does not gain a third generation of overlapping tables (the Aug 21 audit found two already).

## Plan and tasks

Every task changes five files or fewer, ends with its own check, and stays reversible.

### Phase 0. Replay tool and baseline

- [x] **Usage report script.** Done 2026-10-02 on `feat/models-harness`. Four tests pass, and removing the dedupe turns them red ($79.20 against $34.40). `tools/usage_report.py --date D` turns the ad-hoc Oct 1 transcript analysis into a tested script: sessions, tokens, and API-price equivalent by task and model. Files: `tools/usage_report.py`, `tests/test_usage_report.py`, `tests/fixtures/transcripts/*`.
  - Acceptance: run on 2026-10-01, it reproduces the baseline table above.
- [x] **Replay tool.** `tools/replay_day.py --date D --stage synthesis --state-root ~/Projects/mindpattern-v3 --out DIR [--models FILE] [--dry-run]`. It copies this checkout's code into a scratch workspace, snapshots the state root's `memory.db` and `traces.db` with the SQLite backup API, copies `users.json`, the identity files, and the issues before day D, restores the day's trends from the original run's checkpoint, and runs the stage there with `MP_DISABLE_OUTBOUND=1` and traces sent to `DIR/traces`. It fails if the stage's code loaded from anywhere but the scratch copy. Stages: `synthesis` and `research` (`--agents a,b` picks which agents). `site` is the next stage to add.
  - Done 2026-10-02. `tests/test_replay_day.py` (4 tests) drives the real runner, harness, and tracing with a fake `claude` that answers per task. Six mutations were each caught and restored byte for byte: the outbound kill switch dropped, traces left in the workspace, the day's own issue copied in, the models file ignored, trends not restored, and the stage loading code from the code root.
  - Dry run against live state, no model calls: Sep 30 in 2.3 s, a 117 MB `memory.db` and a 43 MB `traces.db` snapshotted, 219 earlier issues, 8 trends restored, live issue unchanged.
  - Real replays, approved 2026-10-02: four Sep 30 synthesis replays and two Oct 2 research replays, results under Phases 1, 3 and 4. Copies live in `data/ramsay/replays/` (gitignored), since `/private/tmp` does not survive a reboot.
- [ ] **Baseline record.** Generate, not hand-copy, the baseline: `tools/usage_report.py` for Oct 1 to Oct 3, the 7-day findings median from `memory.db`, and the policy-violation counts for the last five issues from `mp lint`. Save the command output in this spec's runbook.

### Phase 1. Harness and model config

Built 2026-10-02 on `feat/models-harness`. Full suite: 2,162 passed, 1 skipped, 1 failed (`tests/test_learning_loop.py::TestConsolidateSeesPromotedPatterns`, which also fails on clean `HEAD`). Layer check, the Python 3.11 compile gate, and `git diff --check` pass. 29 guards were each broken on purpose, seen to fail, and restored byte for byte. Two mutations first went uncaught and exposed missing tests (the critic's tool fence, the flush model), which were then added and caught them. Two more turned out harmless, because isolation needs both the working folder and the import path wrong, and were replaced by one mutation that breaks both.

- [x] `core/model_cli.py`: one call path for `claude` and `codex`. `claude -p --output-format stream-json --verbose` and `codex exec --json`, parsed into a `ModelResult` whose `.text` is what `--output-format text` printed, so callers keep their parsing. Plain-text stdout passes through as text. Long prompts go through stdin with no `-` argument (it used to become the prompt's first line). Every call sets `CLAUDE_INVOKED_BY=mindpattern` and `MINDPATTERN_TASK`, and Claude calls run with `--setting-sources project,local --strict-mcp-config`, so the user's own plugins, hooks, and MCP servers stay out (a one-word call cost $0.075 with them and $0.017 without). A route's fallback gets one try on timeout, rate limit, or error.
- [x] `config/models.json` and `core/config.py`, reproducing the routing of 2026-10-02 exactly (pinned by `tests/test_model_config.py`). `python -m core.config check` validates the file. `orchestrator/router.py` now reads it.
- [x] Call sites migrated, old builders deleted: research agents, file agents, and prompts in `orchestrator/agents.py`; the site writer (`run_writer`, which also serves the critic's revision step) and critic; KG extraction (`MP_KG_MODEL` removed); `knowledge/flush.py` (model from the `knowledge_flush` route). `core/llm.py` lost its unused `run`, `ask`, and Sonnet 4.6 default. No model ID remains in production code outside `config/models.json`.
- [x] Tracing storage: `model_calls` and `model_call_steps`, created by the recorder itself because the runner opens `traces.db` without `init_db`. Raw stream and prompt per call in `data/<user>/traces/<date>/<run_id>/`. `MP_TRACE_ROOT` redirects all of it, and `tests/conftest.py` points it at a temp folder for every test. The runner sets run id, date, and phase.
- [x] Subagent capture, from a real Agent-tool capture: the subagent is a child row linked by `parent_call_id`, with its own steps.
- [x] Trace CLI: `python -m orchestrator.trace runs | show [--steps] | call [--full] | grep | usage | prune`.
- [x] Fix found on the way: `_send_alert` ignored `MP_DISABLE_OUTBOUND=1` and would post to Slack from a replay. It now returns without reading the keychain.
- [x] Stream formats confirmed with real captures, now fixtures in `tests/fixtures/cli/`.
- [x] `policies/observability.json`: raw traces kept 90 days, soft budget per run of 3M output tokens or $120 at API prices. LEARN records the run's usage, alerts Slack when it is over, and prunes old trace folders. It never blocks a run.
- [x] Free wins D6: newsletter and story selection moved to Opus 5.5, the subagent block deleted, the writer exemplars and the invented first-person examples rewritten, word-bank hits handed to the Sol editor as its first targets.
- [x] Effort pinned per task. `core/config.py` now rejects a Claude route without an effort setting (Haiku excepted, which takes none), so the user's interactive setting can no longer leak in.
- [x] Codex runs clean: `--ignore-rules` plus plugins, skill search, hooks, apps, browser use, and computer use switched off. A one-word call went from 42K input tokens (it read the unslop skill first) to 18K with no reads. `~/.codex/AGENTS.md` (1.8 KB) still loads; no flag skips it without dropping the login. It currently tells Codex to follow unslop, which matches the writing policy.
- [x] Phase check on real data. Sep 30 synthesis replays, same findings and trends:

| Sep 30 synthesis | Opus 5 (before) | Opus 5.5 | Opus 5.5 plus Sol editor |
|---|---|---|---|
| Overall eval | 0.782 | 0.86 | 0.854 |
| Words | 13,846 | 6,378 | 5,955 |
| Writing-policy violations | 20 | 2 | 3 before the editor, 1 after |
| API-price cost | $2.90 | $2.43 | $2.24 plus Sol on the Codex plan |

  The whole new path on the same day (five deep dives, then Opus 5.5, then the Sol editor) scored 0.862 overall, wrote 5,890 words, and left 2 violations (3 before the editor, which applied 10 of 10 edits). It cost $3.15 at API prices: $0.71 selection, $0.90 for five deep dives, $1.54 writing, plus Sol.

  The length halves because of the model, not the new passes: Opus 5 writes about 13,800 words from the same prompt and Opus 5.5 about 6,000. The eval's length score already prefers the shorter issue (0.1 against 0.85).

  The editor proposed 10 line edits on the real issue and the fact guard applied all 10 after the name check learned to skip ordinary sentence openers ("Beyond that").

### Phase 2. Policies and contracts

- [x] `policies/writing.json` holds the 54 word-bank rules, exported by script and checked equal to the old Python list field by field, plus 16 rules measured from the October research. Each row needs an example its pattern matches; new rows carry a counterexample, the models they target, the measurement date, and a review-by date. `word_bank.py` loads and validates it (982 lines down to 342). `prose_gate.py` reads its em-dash budget from it.
- [x] `policies/editorial.json`: top stories, deep-dive stories, site candidate and issue story caps, the republish tracker threshold. `MP_SITE_ISSUE_STORIES_MAX` and `MP_SITE_CONTENT_MAX_STORIES` are gone. A test holds the selector and writer prompts to the same story count.
- [x] Contracts: `critic_verdict`, `editor_edits`, `research_finding`, `evidence_item`. Codex gets them through `--output-schema`; `core/contracts.py` checks answers in Python for every provider. No new dependency.
- [x] The writer-facing prompts follow the policy they enforce. Every one of the seven passes `word_bank.violations` with zero hits, and a test keeps it that way.

### Phase 3. Research

- [x] `mp` CLI (`mp/cli.py`, launcher `bin/mp`): `finding add`, `findings list`, `seen`, `fetch`, `evidence add`, `lint`, `tells`. `finding add` runs the contract, the research policy engine, a same-run duplicate check, and a 10-day coverage check before it stores anything.
- [x] R1: research agents store each finding as they confirm it. The dispatcher merges stored and printed findings, so an agent that hits the turn cap keeps what it stored. Proven offline by a fake agent that stores two findings through the real `bin/mp` and then prints the turn-cap error.
  - The first real replay stored nothing through `mp`: Claude Code's Bash check refuses a command containing `{"` ("expansion obfuscation"), so every inline-JSON heredoc failed and the findings arrived only through the printed JSON. A probe through the real harness showed a quoted heredoc of `field: value` lines passes apostrophes, `$4`, backticks, and braces through untouched, while a double-quoted `$4` is refused. `mp` now reads field lines on stdin, both prompts teach that form and say to run each `mp` command alone, and `tests/test_mp_cli.py` fails if either prompt example goes back to inline JSON or names a field its contract lacks. `mp fetch --offset` lets an agent read past the first 6,000 characters without piping into `python3`, which Claude Code also refuses.
- [x] R2: agents are told to read pages with `mp fetch --max-chars 6000`. Effect on cached reads to be measured on live runs.
- [x] R3: Sonnet 5.5 research on real sources, four replays of Oct 2 with `hn-researcher` and `skill-finder`. Live Oct 2 on Opus 5.5 gave those two agents 17 findings, none repeating the prior 10 days.

| Oct 2 replay, two agents | New findings | Stored with `mp` | Repeats `mp` rejected | API price |
|---|---|---|---|---|
| Live run, Opus 5.5 | 17 | n/a | n/a | about $5 (Oct 1 average) |
| Sonnet 5.5, inline-JSON prompt | 14 (16 printed, 2 repeats) | 0, every add refused | 0 | $1.75 |
| Sonnet 5.5, field lines | 8 | 8 | 3 | $1.37 |
| Sonnet 5.5, batched, run A | 9 | 4 (`hn-researcher` called `bin/mp`, refused) | 0 | $1.50 |
| Sonnet 5.5, batched, run B | 13 | 6 (same) | 0 | $1.34 |

  Sonnet 5.5 costs about 70% less per agent and finds about a third fewer new stories (mean 11 against 17). The agents stop on their own at 18 to 32 of 35 turns, so the turn cap is not the limit. `config/models.json` keeps research on Sonnet 5.5, as Tayler decided; moving `research_agent` back to `claude-opus-5-5` is one line. Success criterion 6 decides it on live runs. The `bin/mp` refusal is fixed (`Bash(bin/mp *)` is granted too).
- [x] R4: deep-dive pass between story selection and the newsletter (`orchestrator/deep_dive.py`, task `story_deep_dive` on Sonnet 5.5). Sep 30 replay: five deep dives, 33 to 79 s each, 9 to 19 tool steps, $0.12 to $0.27 each. Four stored evidence (22 items). The fifth stored none, because Claude Code refused every inline-JSON `mp evidence add`; the other four found `--json '...'` after the same refusals. Fixed in `mp` the same day (see R1).

### Phase 4. Writing

- [x] Writing-policy rules seeded from the October research (see Phase 2).
- [x] Site writer on Sonnet 5.5 at medium effort. Five Oct 2 stories the live run published, writer only, same effort for both: Sonnet 5.5 passed the site gates on 4 of 5, Sonnet 5 on 3 of 5, at 293 to 350 words and 0 to 2 word-bank hits each. Both failed the arXiv story on a temporal claim ("now has", "today") and an "AI-written" mention; the live run got it through the critic loop.
- [x] Sol critic for site stories with a Sonnet 5.5 fallback. On three published Oct 2 stories it scored 0, 0, and 2, each time quoting a specific unsupported claim the Sonnet 5 critic had passed ("will lend Anthropic $42 billion" for an up-to ceiling).
- [x] Sol editor pass for the newsletter, edit-list contract, fact-preservation guard (`orchestrator/newsletter_editor.py`).
- [ ] Blind comparison on five days. Day one is ready: `open data/ramsay/replays/bakeoff-2026-09-30/compare.html`, pick one, then `tools/bakeoff.py --reveal data/ramsay/replays/bakeoff-2026-09-30`. It pairs the Sep 30 issue that was sent against the full new path on the same findings. The length gap (13,183 against 5,890 words) gives the pair away, so judge which you would rather send. Four more days need a synthesis replay each (about $3 at API prices).

## Commands

```sh
.venv/bin/python3 -m pytest tests/ -x -q                      # full offline suite
.venv/bin/python3 -m pytest tests/test_model_cli.py -x -q      # focused
MP_DISABLE_OUTBOUND=1 .venv/bin/python3 run.py --user ramsay --dry-run --skip-social
.venv/bin/python3 tools/replay_day.py --date 2026-09-30 --stage synthesis --state-root ~/Projects/mindpattern-v3 --out data/ramsay/replays/2026-09-30-a
.venv/bin/python3 tools/replay_day.py --date 2026-10-02 --stage research --agents skill-finder,hn-researcher --state-root ~/Projects/mindpattern-v3 --out data/ramsay/replays/2026-10-02-r
.venv/bin/python3 tools/bakeoff.py --a A.md --b B.md --out data/ramsay/replays/bakeoff-D   # then --reveal
.venv/bin/python3 -m orchestrator.trace --db DIR/traces/traces.db --root DIR/traces show <run> --steps
graphify update . && graphify check-update .
git diff --check && git status --short
```

## Testing strategy

- **Unit tests** call the harness the way pipeline code does and assert literal argv lists and literal parsed usage from recorded output fixtures of both CLIs.
- **Config tests** feed invalid files and assert the run stops before any model call.
- **Equivalence tests** prove each migration keeps behavior: same argv (apart from new flags), same parsed result for the same fixture.
- **Replay checks** run real CLIs on a past day into a scratch root. They spend usage, so each one needs approval first.
- **Watch it fail first.** Per Tayler's rule, every new guard gets broken on purpose, seen to fail, restored byte for byte, and seen to pass.
- Tests stay offline and need no keys, as `AGENTS.md` requires.

## Boundaries

- **Always:** validate config before the first model call. Keep the deterministic fallbacks that exist today. Record usage for every call. Preserve unrelated uncommitted files. Run `graphify update .` after Python changes.
- **Ask first:** schema changes beyond `model_calls` and `model_call_steps`, any new pipeline phase other than R4, switching any default after a bakeoff, any replay that spends usage, commits, pushes, and deploys.
- **Never:** let a model choose control flow. Send email, sync, or post from a replay. Let Sol rewrite facts, numbers, or links. Use `run-launchd.sh` or `start.sh` as test commands. Commit secrets, databases, reports, or `social-config.json`.

## Success criteria

1. Every model call in a run, and every subagent inside one, has a `model_calls` row with provider, model, outcome, tokens, and duration, plus a raw trace file.
2. `trace show <run_id>` renders any run from the last 90 days down to individual tool calls.
3. `grep` finds no model ID outside `config/models.json`.
4. Usage per run is reported by task, model, and provider. Claude usage may rise above the Oct 1 baseline (1.56M output tokens, about $55 at API prices), but every rise traces to a named change, and the soft budget alerts on any run that goes over.
5. No research agent loses its output to the turn cap over five consecutive runs.
6. Findings that pass the gates stay at or above the 7-day median from Phase 0.
7. The newsletter is written by Opus 5.5 and wins the blind comparison on at least 4 of 5 days.
8. Writing-policy violations per issue fall by half against the Phase 0 baseline.
9. At least 20 site stories publish per day, and critic fabrication flags per day fall against baseline.
10. No newsletter is missed during the rollout.

## Open questions

1. **Fable 5.1 for story selection.** It is one call a day, about 3% of usage, at $10 and $50 per million. Worth a bakeoff against Opus 5.5?
2. **Branch.** Start this work on a new branch cut from `fix/restore-learning-loops`, so the verification toolkit and the launcher gate come along?
3. **Codex budget.** How much Sol usage a day is fine? The critic is about 50 calls a day and the editor 1. Phase 1 measures it before Phase 4 relies on it.
4. **Trace retention.** 90 days of raw traces (about 1.7 GB) by default. Longer?
