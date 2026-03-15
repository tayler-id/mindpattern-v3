# Wire Unwired Features Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire 5 built-but-unused modules into the pipeline runner so observability, quality evaluation, entity graph, signals, and research policy validation are active during every run.

**Architecture:** Each module is fully implemented with real code and tests. Integration points are in `orchestrator/runner.py` phase handlers. All integrations are wrapped in try/except so failures are non-fatal (log warning, continue pipeline). No new files created — only `runner.py` is modified.

**Tech Stack:** Python 3.14, SQLite (memory.db + traces.db), existing module APIs

---

## Task 1: PipelineMonitor (Observability + Cost Tracking)

**Files:**
- Modify: `orchestrator/runner.py` — `__init__`, `_execute_from`, `_phase_research`
- Reference: `orchestrator/observability.py` — `PipelineMonitor` class API

**What it does:** Tracks phase durations, agent token usage, cost estimates, and quality history per run.

- [ ] **Step 1: Add import to runner.py**

Add after line 18 (`from .prompt_tracker import PromptTracker`):
```python
from .observability import PipelineMonitor
```

- [ ] **Step 2: Instantiate in `__init__`**

Add after `self.checkpoint = Checkpoint(self.traces_conn)` (line 48):
```python
# Observability — phase timing, cost tracking, quality history
self.monitor = PipelineMonitor(self.traces_conn)
```

- [ ] **Step 3: Wrap phases in `_execute_from`**

In `_execute_from()`, wrap each phase call with monitor timing. Find the block where `handler()` is called and add monitor calls around it:

```python
# Before handler() call:
phase_track_id = None
try:
    phase_track_id = self.monitor.start_phase(self.pipeline.run_id, phase.name)
except Exception as e:
    logger.debug(f"Monitor start_phase failed: {e}")

# Existing handler() call stays as-is
result = handler()

# After handler() call (before the checkpoint.save):
try:
    if phase_track_id is not None:
        tokens = result.get("tokens_used", 0) if isinstance(result, dict) else 0
        self.monitor.end_phase(phase_track_id, status="completed", tokens_used=tokens)
except Exception as e:
    logger.debug(f"Monitor end_phase failed: {e}")
```

Also wrap the error path — in the `except` block for handler failures:
```python
try:
    if phase_track_id is not None:
        self.monitor.end_phase(phase_track_id, status="failed", error=str(e))
except Exception:
    pass
```

- [ ] **Step 4: Record agent metrics in `_phase_research`**

After the `memory.log_agent_run()` call (line 336), add:
```python
try:
    self.monitor.record_agent_metrics(
        agent_name=result.agent_name,
        run_date=self.date_str,
        findings_count=len(result.findings),
        duration_ms=getattr(result, "duration_ms", 0),
        model_used=getattr(result, "model", "sonnet"),
    )
except Exception as e:
    logger.debug(f"Monitor agent metrics failed: {e}")
```

- [ ] **Step 5: Log quality + generate summary in `_phase_learn`**

After `quality = memory.evaluate_run(...)` (line 507), add:
```python
try:
    overall = quality.get("overall_score")
    if overall is not None:
        self.monitor.record_quality(self.date_str, quality)
    summary = self.monitor.generate_summary(self.date_str)
    if summary:
        logger.info(f"Run summary:\n{summary}")
except Exception as e:
    logger.debug(f"Monitor quality/summary failed: {e}")
```

- [ ] **Step 6: Run tests**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v
```

- [ ] **Step 7: Commit**

```bash
git add orchestrator/runner.py
git commit -m "feat: wire PipelineMonitor for phase timing, cost tracking, and quality history"
```

---

## Task 2: NewsletterEvaluator (Quality Scoring)

**Files:**
- Modify: `orchestrator/runner.py` — `_phase_synthesis`
- Reference: `orchestrator/evaluator.py` — `NewsletterEvaluator` class API

**What it does:** Scores newsletters on coverage, dedup, sources, actionability, length, and topic balance. Pure Python, no LLM calls.

- [ ] **Step 1: Add import to runner.py**

Add after the PipelineMonitor import:
```python
from .evaluator import NewsletterEvaluator
```

- [ ] **Step 2: Evaluate newsletter after synthesis**

In `_phase_synthesis()`, after `report_path.write_text(self.newsletter_text)` (line 457) and before the return statement, add:

```python
# Evaluate newsletter quality (deterministic, no LLM)
try:
    evaluator = NewsletterEvaluator(self.db)
    agent_reports = [
        {"agent": f["agent"], "title": f["title"], "importance": f["importance"]}
        for f in today_findings
    ]
    prefs_list = memory.list_preferences(self.db, effective=True)
    eval_scores = evaluator.evaluate(self.newsletter_text, agent_reports, prefs_list)
    logger.info(
        f"Newsletter quality: overall={eval_scores.get('overall', 0):.2f} "
        f"(coverage={eval_scores.get('coverage', 0):.2f}, "
        f"sources={eval_scores.get('sources', 0):.2f}, "
        f"length={eval_scores.get('length', 0):.2f})"
    )
    self._newsletter_eval = eval_scores  # store for _phase_learn
except Exception as e:
    logger.warning(f"Newsletter evaluation failed (non-critical): {e}")
    self._newsletter_eval = None
```

- [ ] **Step 3: Initialize `_newsletter_eval` in `__init__`**

Add after `self.newsletter_text`:
```python
self._newsletter_eval: dict | None = None
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add orchestrator/runner.py
git commit -m "feat: wire NewsletterEvaluator for post-synthesis quality scoring"
```

---

## Task 3: Signals (Cross-Pipeline Feedback Loops)

**Files:**
- Modify: `orchestrator/runner.py` — `_phase_social`, `_phase_research`
- Reference: `memory/signals.py` — `store_signal()`, `get_signal_context()`

**What it does:** Stores engagement signals from social pipeline, feeds them back into research agent context so high-engagement topics get more coverage.

- [ ] **Step 1: Store engagement signals after social posting**

In `_phase_social()`, after `result = pipeline.run()` (line 588), add:

```python
# Store engagement signals for cross-pipeline feedback
try:
    topic = result.get("topic", "")
    if topic and result.get("posts"):
        memory.store_signal(
            self.db,
            pipeline="social",
            signal_type="content_posted",
            topic=topic,
            strength=0.3,
            evidence=f"Posted to {len(result['posts'])} platform(s)",
            run_date=self.date_str,
        )
except Exception as e:
    logger.debug(f"Signal storage failed: {e}")
```

- [ ] **Step 2: Include signal context in research agent dispatch**

In `_phase_research()`, before `self.agent_results = agent_dispatch.dispatch_research_agents(...)` (line 278), add:

```python
# Get signal context for research agents (feedback from social/engagement)
signal_context = ""
try:
    signal_context = memory.get_signal_context(self.db, days=14)
    if signal_context:
        logger.info(f"Signal context: {len(signal_context)} chars for agent dispatch")
except Exception as e:
    logger.debug(f"Signal context failed: {e}")
```

Note: The `signal_context` string is available but `dispatch_research_agents` may not accept it yet. If it doesn't, log it for now and wire the parameter in a follow-up.

- [ ] **Step 3: Run tests**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add orchestrator/runner.py
git commit -m "feat: wire cross-pipeline signals for research-social feedback loop"
```

---

## Task 4: Entity Graph (Knowledge Extraction)

**Files:**
- Modify: `orchestrator/runner.py` — `_phase_learn`
- Reference: `memory/graph.py` — `store_relationship()`

**What it does:** Extracts entity relationships from high-importance findings and stores them in the entity graph for knowledge accumulation.

- [ ] **Step 1: Extract and store entity relationships in `_phase_learn`**

After the consolidate/promote/prune block (line 546), add:

```python
# Extract entity relationships from today's high-importance findings
entities_stored = 0
try:
    high_findings = self.db.execute(
        "SELECT id, agent, title, source_name FROM findings "
        "WHERE run_date = ? AND importance = 'high'",
        (self.date_str,),
    ).fetchall()
    for f in high_findings:
        # Store agent-finding relationship
        if f["source_name"] and f["agent"]:
            memory.store_relationship(
                self.db,
                entity_a=f["source_name"],
                relationship="reported_by",
                entity_b=f["agent"],
                entity_a_type="source",
                entity_b_type="agent",
                finding_id=f["id"],
            )
            entities_stored += 1
    if entities_stored:
        logger.info(f"Entity graph: {entities_stored} relationships stored")
except Exception as e:
    logger.debug(f"Entity graph extraction failed: {e}")
```

- [ ] **Step 2: Include entity count in return dict**

Add `"entities_stored": entities_stored,` to the return dict.

- [ ] **Step 3: Run tests**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add orchestrator/runner.py
git commit -m "feat: wire entity graph for knowledge extraction from high-importance findings"
```

---

## Task 5: Research Policy Validation

**Files:**
- Modify: `orchestrator/runner.py` — `_phase_research`
- Reference: `policies/engine.py` — `PolicyEngine` class

- [ ] **Step 1: Check if PolicyEngine has research validation**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && grep -n "load_research\|validate_agent\|research" policies/engine.py | head -20
```

If `load_research()` or a research validation method exists, proceed. If not, skip this task (social validation is already wired).

- [ ] **Step 2: Add validation after finding storage (if method exists)**

In `_phase_research()`, after `memory.store_finding(...)` (line 310), add policy check:

```python
# Validate finding against research policies
try:
    from policies.engine import PolicyEngine
    policy = PolicyEngine.load_research()
    errors = policy.validate(finding)
    if errors:
        logger.warning(f"Policy violation in {result.agent_name}: {errors}")
except Exception:
    pass  # Policy validation is advisory, not blocking
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add orchestrator/runner.py
git commit -m "feat: wire research policy validation for agent output quality gates"
```

---

## Task 6: Autoresearch Launchd Plist

**Files:**
- Create: `~/Library/LaunchAgents/com.taylerramsay.autoresearch.plist`
- Reference: `autoresearch.py` — entry point, `~/Library/LaunchAgents/com.taylerramsay.daily-research.plist` — format template

- [ ] **Step 1: Create plist**

Create `~/Library/LaunchAgents/com.taylerramsay.autoresearch.plist` matching the daily-research plist format:
- Label: `com.taylerramsay.autoresearch`
- ProgramArguments: `/opt/homebrew/bin/python3`, `/Users/taylerramsay/Projects/mindpattern-v3/autoresearch.py`, `--user`, `ramsay`
- WorkingDirectory: `/Users/taylerramsay/Projects/mindpattern-v3`
- StartCalendarInterval: Hour=2, Minute=0 (2 AM — after daily research at 7 AM has quality data)
- StandardOutPath: `/Users/taylerramsay/Projects/mindpattern-v3/reports/autoresearch-stdout.log`
- StandardErrorPath: `/Users/taylerramsay/Projects/mindpattern-v3/reports/autoresearch-stderr.log`
- ExitTimeOut: 3600
- EnvironmentVariables: PATH, HOME

- [ ] **Step 2: Load and verify**

```bash
launchctl load ~/Library/LaunchAgents/com.taylerramsay.autoresearch.plist
launchctl list | grep autoresearch
```

- [ ] **Step 3: Test dry run**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 autoresearch.py --dry-run --user ramsay
```

---

## Task 7: Push and Verify

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v
```
Expected: All 253+ tests pass.

- [ ] **Step 2: Push to GitHub**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && git push origin main
```

---

## Deferred: Agent Evolution

**NOT included in this plan.** `memory/evolution.py` (562 lines) enables dynamic agent spawn/retire/merge based on performance and user preferences. This is architecturally significant — it changes how agents are loaded from static config to dynamic DB. Needs its own spec + plan.
