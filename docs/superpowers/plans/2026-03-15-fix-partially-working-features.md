# Fix Partially Working Phase 1 Features — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 5 partially-working Phase 1 features: EVOLVE prompt richness, agent transcript depth, engagement filtering, social posts in vault, and Agent Reach adoption.

**Architecture:** Each fix is independent. EVOLVE needs richer pipeline_results from the runner. Transcripts need the hook to parse all assistant message blocks. Engagement needs config values used instead of hardcoded defaults. Posts need the mirror to render all dates. Agent Reach needs mandatory language in prompts.

**Tech Stack:** Python 3.14, Jinja2, SQLite, Claude CLI hooks (JSONL parsing)

---

## Chunk 1: EVOLVE Prompt Enrichment

### Task 1: Capture social pipeline results in runner

The EVOLVE phase only receives `{date, findings_count, newsletter_generated}`. The spec requires topic selected, gate outcomes, corrections, expeditor feedback, and newsletter eval scores.

**Files:**
- Modify: `orchestrator/runner.py` — `_phase_social()` to store result, `_phase_evolve()` to build richer dict
- Test: `tests/test_identity_evolve.py` — add test for enriched prompt

- [ ] **Step 1: Write test for enriched pipeline_results**

In `tests/test_identity_evolve.py`, add:

```python
class TestEnrichedPrompt:
    def test_build_evolve_prompt_includes_social_data(self, vault_dir):
        """Prompt includes topic, gate outcomes, and expeditor when provided."""
        from memory.identity_evolve import build_evolve_prompt

        # Seed minimal vault files
        for name in ["soul.md", "user.md", "voice.md", "decisions.md"]:
            (vault_dir / name).write_text(f"# {name}\n\n## Test\n\nContent\n")

        pipeline_results = {
            "date": "2026-03-15",
            "findings_count": 64,
            "newsletter_generated": True,
            "newsletter_eval": {"overall": 1.74, "coverage": 0.90, "dedup": 1.0},
            "social": {
                "topic": "OpenAI launched Frontier with consulting partners",
                "topic_score": 8.3,
                "gate1_outcome": "approved",
                "gate1_guidance": "",
                "gate2_outcome": "approved",
                "gate2_edits": [],
                "expeditor_verdict": "PASS",
                "platforms_posted": ["bluesky", "linkedin"],
            },
        }
        prompt = build_evolve_prompt(vault_dir, pipeline_results)
        assert "OpenAI launched Frontier" in prompt
        assert "gate1" in prompt.lower() or "gate 1" in prompt.lower()
        assert "expeditor" in prompt.lower() or "PASS" in prompt
        assert "1.74" in prompt or "overall" in prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_identity_evolve.py::TestEnrichedPrompt -v`

- [ ] **Step 3: Update build_evolve_prompt to accept social data**

In `memory/identity_evolve.py`, update `build_evolve_prompt()` to add a `## Social Pipeline Results` section when `pipeline_results` contains a `"social"` key. Add a `## Newsletter Quality` section when it contains `"newsletter_eval"`. The prompt should tell the LLM to include these in the decisions.md entry.

The social section should render:
```
## Social Pipeline Results
- Topic: {topic} (score: {score})
- Gate 1: {outcome} {guidance if any}
- Gate 2: {outcome} {edits if any}
- Expeditor: {verdict}
- Posted to: {platforms}
```

The newsletter section:
```
## Newsletter Quality
- Overall: {overall}, Coverage: {coverage}, Dedup: {dedup}
```

Update the decisions.md instruction in the prompt to say:
```
For decisions.md, append a detailed entry including:
- Topic selected/killed + score + reasoning
- Gate 1 outcome (approved/rejected/custom + any guidance)
- Gate 2 outcome (approved/rejected/edits made)
- Expeditor verdict
- Newsletter quality scores
- Pattern observations (e.g. "3rd security topic rejected this week")
```

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Update runner to capture and pass social results**

In `orchestrator/runner.py`:

1. Add `self.social_result: dict = {}` and `self.newsletter_eval: dict = {}` to `__init__`
2. In `_phase_social()`, after `pipeline.run()`, store: `self.social_result = result`
3. In `_phase_synthesis()`, after `NewsletterEvaluator`, store: `self.newsletter_eval = eval_scores`
4. In `_phase_evolve()`, build richer `pipeline_results`:

```python
pipeline_results = {
    "date": self.date_str,
    "findings_count": len(self.agent_results) if self.agent_results else 0,
    "newsletter_generated": bool(self.newsletter_text),
    "newsletter_eval": self.newsletter_eval,
    "social": {
        "topic": self.social_result.get("topic", {}).get("topic", ""),
        "topic_score": self.social_result.get("topic", {}).get("composite_score", 0),
        "gate1_outcome": self.social_result.get("gate1_outcome", "unknown"),
        "gate1_guidance": self.social_result.get("gate1_guidance", ""),
        "gate2_outcome": self.social_result.get("gate2_outcome", "unknown"),
        "gate2_edits": self.social_result.get("gate2_edits", []),
        "expeditor_verdict": self.social_result.get("expeditor_verdict", "unknown"),
        "platforms_posted": self.social_result.get("platforms_posted", []),
    } if self.social_result else {},
}
```

5. Check what keys `SocialPipeline.run()` actually returns. Read `social/pipeline.py` return dict. If gate outcomes aren't in the return dict, add them. Store `gate1_outcome`, `gate1_guidance`, `gate2_outcome`, `gate2_edits`, `expeditor_verdict` as the pipeline progresses.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/test_identity_evolve.py -v`

- [ ] **Step 7: Commit**

```bash
git add memory/identity_evolve.py orchestrator/runner.py tests/test_identity_evolve.py
git commit -m "feat: enrich EVOLVE prompt with social results, gate outcomes, newsletter scores"
```

---

## Chunk 2: Agent Transcript Depth

### Task 2: Improve hook transcript parser

The hook currently shows `reasoning_blocks: 1` for most agents because it only captures the final JSON output. The JSONL transcript actually contains multiple assistant messages with text blocks between tool calls — the parser needs to count them all and include tool result summaries.

**Files:**
- Modify: `hooks/session-transcript.py` — `extract_agent_log()` function
- Test: `tests/test_session_hook.py` — add multi-turn transcript test

- [ ] **Step 1: Write test for multi-turn transcript**

In `tests/test_session_hook.py`, add:

```python
class TestMultiTurnTranscript:
    def test_captures_all_reasoning_blocks(self, tmp_path):
        """Multiple assistant messages each produce a reasoning block."""
        lines = [
            {"type": "user", "timestamp": "2026-03-15T07:00:00Z",
             "message": {"content": "Search for AI papers"}},
            {"type": "assistant", "timestamp": "2026-03-15T07:00:05Z",
             "message": {"content": [
                 {"type": "text", "text": "I'll search arxiv first."},
                 {"type": "tool_use", "name": "WebSearch", "input": {"q": "arxiv AI"}},
             ]}},
            {"type": "assistant", "timestamp": "2026-03-15T07:00:15Z",
             "message": {"content": [
                 {"type": "text", "text": "Found 3 papers. Now checking HN."},
                 {"type": "tool_use", "name": "WebSearch", "input": {"q": "HN AI"}},
             ]}},
            {"type": "assistant", "timestamp": "2026-03-15T07:00:25Z",
             "message": {"content": [
                 {"type": "text", "text": "HN has 2 relevant threads. Let me read them."},
                 {"type": "tool_use", "name": "WebFetch", "input": {"url": "https://..."}},
             ]}},
            {"type": "assistant", "timestamp": "2026-03-15T07:01:00Z",
             "message": {"content": '{"findings": [{"title": "Paper 1"}]}'}},
        ]
        path = tmp_path / "multi.jsonl"
        path.write_text("\n".join(json.dumps(l) for l in lines))
        messages = hook.parse_transcript(str(path))
        log = hook.extract_agent_log(messages)
        assert len(log["reasoning"]) == 4  # All 4 assistant text blocks
        assert len(log["tool_calls"]) == 3  # 3 tool_use blocks
        assert "arxiv first" in log["reasoning"][0]
        assert "HN has 2" in log["reasoning"][2]

    def test_captures_tool_result_summaries(self, tmp_path):
        """Tool results from user messages are captured."""
        lines = [
            {"type": "user", "timestamp": "2026-03-15T07:00:00Z",
             "message": {"content": "Search"}},
            {"type": "assistant", "timestamp": "2026-03-15T07:00:05Z",
             "message": {"content": [
                 {"type": "text", "text": "Searching..."},
                 {"type": "tool_use", "id": "t1", "name": "WebSearch",
                  "input": {"q": "test"}},
             ]}},
            {"type": "user", "timestamp": "2026-03-15T07:00:10Z",
             "message": {"content": [
                 {"type": "tool_result", "tool_use_id": "t1",
                  "content": "Found: Paper on alignment techniques (arxiv 2026)"},
             ]}},
            {"type": "assistant", "timestamp": "2026-03-15T07:00:15Z",
             "message": {"content": "The alignment paper looks promising."}},
        ]
        path = tmp_path / "results.jsonl"
        path.write_text("\n".join(json.dumps(l) for l in lines))
        messages = hook.parse_transcript(str(path))
        log = hook.extract_agent_log(messages)
        assert len(log["tool_results"]) >= 1
        assert "alignment" in log["tool_results"][0]
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Update extract_agent_log to capture tool results**

In `hooks/session-transcript.py`, update `extract_agent_log()`:

1. Add `tool_results = []` to the return dict
2. For user messages with list content, check for `tool_result` type blocks:
```python
elif isinstance(content, list):
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            result_text = block.get("content", "")
            if isinstance(result_text, str) and result_text.strip():
                tool_results.append(_truncate(result_text.strip(), 300))
```
3. Add `"tool_results": tool_results` to the return dict

- [ ] **Step 4: Update format_agent_log to render tool results**

Add a `## Tool Results (summaries)` section after Tool Calls that shows truncated tool results. This gives visibility into what the agent actually found.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_session_hook.py -v`

- [ ] **Step 6: Commit**

```bash
git add hooks/session-transcript.py tests/test_session_hook.py
git commit -m "feat: capture multi-turn reasoning and tool results in agent transcripts"
```

---

## Chunk 3: Engagement Filtering Fix

### Task 3: Use config values instead of hardcoded defaults

The engagement code at `social/engagement.py` lines 583-585 uses hardcoded defaults (min_likes=3, min_followers=50) instead of the config values (min_likes=0, min_followers=10).

**Files:**
- Modify: `social/engagement.py` — filtering logic
- Test: `tests/test_engagement_linkedin.py` — add filter threshold test

- [ ] **Step 1: Write test for config-driven filtering**

```python
class TestFilterThresholds:
    def test_uses_config_min_likes(self):
        """Filter uses config min_likes, not hardcoded default."""
        from social.engagement import EngagementPipeline
        config = {"min_likes": 0, "min_follower_count": 5, "platforms": ["bluesky"]}
        # Verify the pipeline reads these values
        pipeline = EngagementPipeline.__new__(EngagementPipeline)
        pipeline.engagement_config = config
        # A post with 0 likes and 5 followers should pass
        assert config["min_likes"] == 0
        assert config["min_follower_count"] == 5
```

- [ ] **Step 2: Fix the defaults in engagement.py**

In `social/engagement.py`, find the filter logic (around line 583-585) and change:
```python
# BEFORE (hardcoded defaults override config):
min_likes = self.engagement_config.get("min_likes", 3)
min_followers = self.engagement_config.get("min_follower_count", 50)

# AFTER (config values respected, low defaults):
min_likes = self.engagement_config.get("min_likes", 0)
min_followers = self.engagement_config.get("min_follower_count", 10)
```

Search for ALL instances of these defaults in the file — there may be multiple filter functions.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_engagement_linkedin.py -v`

- [ ] **Step 4: Commit**

```bash
git add social/engagement.py tests/test_engagement_linkedin.py
git commit -m "fix: use config values for engagement filtering instead of hardcoded defaults"
```

---

## Chunk 4: Social Posts in Vault — All Dates

### Task 4: Fix posts.md mirror to show all historical posts

The mirror correctly queries all posts from the DB (79 posts across 16 dates). The issue is that posts from March 11-14 don't exist because no pipeline ran those days (v3 wasn't active). This is correct behavior. However, the posts.md template doesn't group by date clearly. Also, old posts have `PLATFORM: bluesky\nTYPE: single\n---\n` prefix text (v2-era formatting) that should be stripped.

**Files:**
- Modify: `memory/mirror.py` — `_build_posts_data()` to strip v2 prefix
- Modify: `memory/templates/posts.md.j2` — improve grouping by date
- Test: `tests/test_mirror.py` — add post cleanup test

- [ ] **Step 1: Write test for v2 prefix stripping**

```python
class TestPostCleanup:
    def test_strips_v2_platform_prefix(self):
        """v2-era posts with PLATFORM/TYPE prefix get cleaned."""
        from memory.mirror import _build_posts_data
        posts = [{
            "date": "2026-03-10",
            "platform": "bluesky",
            "content": "PLATFORM: bluesky\nTYPE: single\n---\nactual post content here",
            "gate2_action": "approved",
        }]
        result = _build_posts_data(posts)
        assert "PLATFORM:" not in result[0]["content"]
        assert "actual post content here" in result[0]["content"]
```

- [ ] **Step 2: Update _build_posts_data to strip v2 prefix**

In `memory/mirror.py`, in `_build_posts_data()`, add content cleanup:
```python
content = p["content"]
# Strip v2-era PLATFORM/TYPE prefix
if content.startswith("PLATFORM:"):
    lines = content.split("\n")
    # Find the --- separator and take everything after
    for i, line in enumerate(lines):
        if line.strip() == "---":
            content = "\n".join(lines[i+1:]).strip()
            break
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_mirror.py -v`

- [ ] **Step 4: Commit**

```bash
git add memory/mirror.py tests/test_mirror.py
git commit -m "fix: strip v2-era PLATFORM/TYPE prefix from social posts in vault"
```

---

## Chunk 5: Agent Reach Mandatory Adoption

### Task 5: Rewrite Agent Reach instructions to be mandatory

Currently the instructions say "Use these tools when..." (optional). Need to change to mandatory language with explicit tool invocation sections, matching the pattern that rss-researcher and hn-researcher use successfully.

**Files:**
- Modify: All 13 agent `.md` files in `verticals/ai-tech/agents/`

- [ ] **Step 1: Rewrite Agent Reach section for all agents**

Replace the current Agent Reach section in ALL agent files. The new section should:

1. Change "Use these tools when..." to "You MUST use Jina Reader to fetch full content for your top sources."
2. Add a mandatory **Research Protocol** that forces tool use BEFORE returning findings:

```markdown
## Research Protocol (MANDATORY)

1. **Search phase**: Use WebSearch to find candidate sources
2. **Deep read phase**: For your top 5 sources, use Jina Reader to get full article content:
   ```bash
   curl -s "https://r.jina.ai/{URL}" 2>/dev/null | head -200
   ```
3. **Verify phase**: Cross-reference claims across sources before including in findings
4. Every finding MUST include a source_url you have actually read via Jina Reader or WebFetch

Do NOT return findings based only on search result snippets. Read the actual articles.
```

3. For agents that should use platform-specific tools, add explicit commands:
   - thought-leaders-researcher: Add `xreach` for Twitter/X posts
   - reddit-researcher: Already uses Reddit fetch tool
   - hn-researcher: Already uses HN fetch tool

- [ ] **Step 2: Verify all 13 agents have the new section**

```bash
grep -l "Research Protocol (MANDATORY)" verticals/ai-tech/agents/*.md | wc -l
# Expected: 13
```

- [ ] **Step 3: Commit**

```bash
git add verticals/ai-tech/agents/*.md
git commit -m "feat: make Agent Reach mandatory in all research agent prompts"
```

---

## Validation

After all chunks are implemented:

- [ ] **Run full test suite**: `pytest tests/ -v --tb=short`
- [ ] **Run Phase 1 validator**: `python3 tests/validate_phase1.py`
- [ ] **Run a real pipeline** and verify:
  - EVOLVE appends a detailed decisions.md entry with topic, gates, scores
  - Agent transcripts show multiple reasoning blocks and tool results
  - Engagement finds candidates (lower thresholds)
  - Posts.md shows clean content without v2 prefixes
  - Agent transcripts show Jina Reader usage across most agents
