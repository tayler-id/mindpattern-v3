#!/usr/bin/env python3
"""Overnight self-improvement loop.

Tests one improvement hypothesis per run. Runs as separate launchd cron.
Inspired by Karpathy's autoresearch pattern.

Usage:
    python3 autoresearch.py                    # Run once
    python3 autoresearch.py --dry-run          # Generate hypotheses but don't apply
"""
import argparse, json, logging, os, re, subprocess, sys, time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("autoresearch")

ALLOWED_DIRS = ["verticals/ai-tech/agents/", "prompts/"]
ALLOWED_FILES = ["config.json"]
QUALITY_THRESHOLD = 0.005  # must beat baseline by this to adopt
MAX_HYPOTHESES = 3


def setup_logging() -> None:
    """Dual logging: stderr (human) + JSONL file (machine)."""
    log_dir = PROJECT_ROOT / "reports"
    log_dir.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))
    fh = logging.FileHandler(str(log_dir / f"autoresearch-{date_str}.jsonl"))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(fh)


# ── Context ────────────────────────────────────────────────────────────────

def _load_quality_context(db) -> dict:
    """Load quality scores, failures, agent perf for the hypothesis prompt."""
    import memory
    ctx = {"latest_quality": None, "avg_7day": None, "recent_failures": [],
           "agent_performance": [], "failure_categories": {}, "recent_changes": []}

    row = db.execute(
        "SELECT * FROM run_quality ORDER BY run_date DESC LIMIT 1").fetchone()
    if row:
        ctx["latest_quality"] = {k: row[k] for k in [
            "run_date", "overall_score", "total_findings", "unique_sources",
            "high_value_count", "trending_coverage", "dedup_rate",
            "agent_utilization", "source_diversity"]}
        ctx["latest_quality"]["date"] = ctx["latest_quality"].pop("run_date")

    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    avg = db.execute(
        "SELECT AVG(overall_score) as s FROM run_quality WHERE run_date >= ?",
        (cutoff,)).fetchone()
    if avg and avg["s"] is not None:
        ctx["avg_7day"] = round(avg["s"], 3)

    ctx["recent_failures"] = [
        {"category": f["category"], "lesson": f["lesson"], "date": f["run_date"]}
        for f in memory.recent_failures(db, limit=5)]

    for r in db.execute("SELECT DISTINCT agent FROM run_log ORDER BY agent").fetchall():
        perf = memory.check_agent_performance(db, r["agent"], runs=5)
        if perf["consecutive_zero_high_value"] >= 2:
            ctx["agent_performance"].append(perf)

    ctx["failure_categories"] = memory.failure_categories(db, days=30)

    notes = db.execute(
        """SELECT content FROM agent_notes
           WHERE agent='autoresearch' AND note_type='experiment'
           ORDER BY created_at DESC LIMIT 5""").fetchall()
    ctx["recent_changes"] = [
        json.loads(n["content"]) if n["content"].startswith("{")
        else {"note": n["content"]} for n in notes]
    return ctx


# ── Hypothesis Generation ─────────────────────────────────────────────────

def _modifiable_files() -> list[str]:
    """List all files the optimizer is allowed to touch."""
    files = []
    for d in ALLOWED_DIRS:
        dp = PROJECT_ROOT / d
        if dp.exists():
            files.extend(str(f.relative_to(PROJECT_ROOT)) for f in sorted(dp.glob("*.md")))
    files.extend(f for f in ALLOWED_FILES if (PROJECT_ROOT / f).exists())
    return files


def _build_hypothesis_prompt(ctx: dict) -> str:
    """Build the prompt for generating improvement hypotheses."""
    # Quality summary
    if ctx["latest_quality"]:
        q = ctx["latest_quality"]
        qt = (f"Latest run ({q['date']}): score={q['overall_score']:.3f}, "
              f"findings={q['total_findings']}, high_value={q['high_value_count']}, "
              f"sources={q['unique_sources']}\n"
              f"  utilization={q['agent_utilization']:.3f}, diversity={q['source_diversity']:.3f}, "
              f"trending={q['trending_coverage']:.3f}, dedup={q['dedup_rate']:.3f} (lower=better)\n"
              f"  7-day avg: {ctx['avg_7day'] or 'N/A'}")
    else:
        qt = "No quality data yet."

    ft = "\n".join(f"- [{f['category']}] {f['lesson']} ({f['date']})"
                   for f in ctx["recent_failures"]) or "None."
    at = "\n".join(f"- {a['agent']}: {a['consecutive_zero_high_value']} zero-high-value runs"
                   for a in ctx["agent_performance"]) or "All OK."
    ct = ", ".join(f"{k}:{v}" for k, v in ctx["failure_categories"].items()) or "None."
    rt = "\n".join(f"- {json.dumps(c, default=str)}"
                   for c in ctx["recent_changes"]) or "None."
    mf = "\n".join(f"- {f}" for f in _modifiable_files())

    return f"""You are a research system optimizer. Generate exactly {MAX_HYPOTHESES} improvement hypotheses.

## Performance
{qt}

## Recent Failures
{ft}

## Underperforming Agents
{at}

## Failure Categories (30d)
{ct}

## Previous Experiments (do NOT repeat)
{rt}

## Modifiable Files
{mf}

## Rules
1. Each hypothesis modifies EXACTLY ONE file from the list above.
2. Small, specific changes only: prompt tweaks, search strategy, thresholds.
3. NO code changes, dependency changes, or infrastructure changes.
4. For agent .md: adjust search strategy, output format, focus areas, sources.
5. For prompt .md: adjust instructions, examples, scoring criteria.
6. For config.json: adjust thresholds and non-structural settings only.
7. Target the weakest metric or most frequent failure category.
8. Do NOT repeat previous experiments.

Output ONLY valid JSON:
{{"hypotheses": [{{"id": 1, "change": "description", "file": "path", "reason": "why", "expected_impact": "metric +X", "priority": "high|medium|low"}}]}}"""


def _generate_hypotheses(ctx: dict) -> list[dict]:
    """One Sonnet call to generate improvement hypotheses."""
    from orchestrator.agents import run_claude_prompt
    prompt = _build_hypothesis_prompt(ctx)
    output, exit_code = run_claude_prompt(
        prompt, "learnings_update", allowed_tools=["Read", "Glob", "Grep"])

    if exit_code != 0 or not output.strip():
        logger.error("Hypothesis generation failed (exit %d)", exit_code)
        return []

    try:
        data = json.loads(output.strip())
    except json.JSONDecodeError:
        m = re.search(r'\{[\s\S]*"hypotheses"[\s\S]*\}', output)
        if not m:
            logger.error("No hypothesis JSON found in output")
            return []
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            logger.error("Could not parse hypothesis JSON")
            return []

    hypotheses = data.get("hypotheses", [])
    if not isinstance(hypotheses, list):
        return []

    valid = []
    for h in hypotheses:
        if not isinstance(h, dict):
            continue
        if not all(k in h for k in ("change", "file", "reason", "expected_impact")):
            continue
        fp = h["file"]
        ok = any(fp.startswith(d) for d in ALLOWED_DIRS) or fp in ALLOWED_FILES
        if not ok or not (PROJECT_ROOT / fp).exists():
            logger.warning("Skipping hypothesis for %s (disallowed or missing)", fp)
            continue
        valid.append(h)

    logger.info("Generated %d valid hypotheses (of %d)", len(valid), len(hypotheses))
    return valid


def _pick_hypothesis(hypotheses: list[dict]) -> dict | None:
    """Pick highest-priority hypothesis. high > medium > low."""
    if not hypotheses:
        return None
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(hypotheses, key=lambda h: order.get(h.get("priority", "medium"), 1))[0]


# ── Change Application ────────────────────────────────────────────────────

def _apply_change(hypothesis: dict) -> bool:
    """Use claude -p to apply the change. Returns True if file was modified."""
    from orchestrator.agents import run_claude_prompt
    target = PROJECT_ROOT / hypothesis["file"]
    if not target.exists():
        return False

    original = target.read_text()
    original_len = len(original)

    prompt = f"""Make a targeted edit to improve a research agent system.

File: {hypothesis['file']}
Change: {hypothesis['change']}
Reason: {hypothesis['reason']}

Instructions:
1. Read the file at {hypothesis['file']}
2. Make the MINIMAL change described. Do not rewrite the whole file.
3. Write the modified file back.
4. Output ONLY "DONE" or "FAILED: reason".

CRITICAL: Smallest possible change. Do not restructure unrelated sections."""

    output, exit_code = run_claude_prompt(
        prompt, "learnings_update",
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"])

    if exit_code != 0:
        logger.error("Change application failed (exit %d)", exit_code)
        return False
    if not target.exists():
        logger.error("File disappeared after edit: %s", target)
        return False

    new = target.read_text()
    if new == original:
        logger.warning("File not modified")
        return False

    # Sanity: reject drastic size changes
    ratio = len(new) / max(original_len, 1)
    if ratio < 0.5 or ratio > 2.0:
        logger.error("Size ratio %.2f out of bounds, reverting", ratio)
        target.write_text(original)
        return False

    logger.info("Applied to %s (%d -> %d bytes)", hypothesis["file"], original_len, len(new))
    return True


# ── Simulated Research ─────────────────────────────────────────────────────

def _simulate_research(user_id: str, date_str: str) -> dict:
    """Run research agents only (no newsletter/email). Returns quality dict."""
    import memory
    from orchestrator.runner import ResearchPipeline

    pipeline = ResearchPipeline(user_id, date_str)
    try:
        pipeline._phase_init()
        pipeline._phase_trend_scan()
        result = pipeline._phase_research()
        quality = memory.evaluate_run(pipeline.db, date_str)
        logger.info("Simulation: %d findings, score %.3f",
                     result.get("findings_stored", 0), quality.get("overall_score", 0))
        return quality
    except Exception as e:
        logger.error("Simulation failed: %s", e, exc_info=True)
        return {"error": str(e), "overall_score": 0.0}
    finally:
        pipeline.close()


# ── Git ────────────────────────────────────────────────────────────────────

def _git(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a git command, return CompletedProcess."""
    return subprocess.run(
        ["git"] + args, capture_output=True, text=True,
        timeout=timeout, cwd=str(PROJECT_ROOT))

def _git_is_repo() -> bool:
    try:
        return _git(["rev-parse", "--git-dir"], timeout=10).returncode == 0
    except Exception:
        return False

def _git_is_clean() -> bool:
    try:
        r = _git(["status", "--porcelain"])
        return r.returncode == 0 and not r.stdout.strip()
    except Exception:
        return False

def _git_branch(name: str) -> bool:
    """Create and checkout branch. Returns True on success."""
    _git(["checkout", "main"])
    r = _git(["checkout", "-b", name])
    if r.returncode != 0:
        logger.error("git checkout -b failed: %s", r.stderr)
        return False
    logger.info("Created branch: %s", name)
    return True

def _git_commit(message: str) -> bool:
    """Stage allowed dirs/files and commit."""
    for d in ALLOWED_DIRS:
        dp = PROJECT_ROOT / d
        if dp.exists():
            _git(["add", str(dp)])
    for f in ALLOWED_FILES:
        fp = PROJECT_ROOT / f
        if fp.exists():
            _git(["add", str(fp)])
    r = _git(["commit", "-m", message])
    if r.returncode != 0:
        logger.error("git commit failed: %s", r.stderr)
        return False
    return True

def _git_merge_main(branch: str) -> bool:
    """Merge branch to main and delete it."""
    _git(["checkout", "main"])
    r = _git(["merge", branch, "--no-ff", "-m", f"autoresearch: adopt {branch}"])
    if r.returncode != 0:
        logger.error("git merge failed: %s", r.stderr)
        return False
    _git(["branch", "-d", branch])
    logger.info("Merged %s to main", branch)
    return True

def _git_cleanup(branch: str):
    """Delete branch, return to main."""
    _git(["checkout", "main"])
    _git(["branch", "-D", branch])
    logger.info("Cleaned up branch: %s", branch)


# ── Experiment Logging ─────────────────────────────────────────────────────

def _log_experiment(db, date_str: str, hypothesis: dict, adopted: bool,
                    q_before: float, q_after: float) -> None:
    """Log experiment outcome to agent_notes + failure_lessons if rejected."""
    import memory
    now = datetime.now().isoformat()
    record = {"hypothesis": hypothesis, "adopted": adopted,
              "quality_before": q_before, "quality_after": q_after,
              "delta": round(q_after - q_before, 4), "date": date_str}

    db.execute(
        """INSERT INTO agent_notes (run_date, agent, note_type, content, created_at)
           VALUES (?, 'autoresearch', 'experiment', ?, ?)""",
        (date_str, json.dumps(record), now))

    if adopted:
        db.execute(
            """INSERT INTO agent_notes (run_date, agent, note_type, content, created_at)
               VALUES (?, 'autoresearch', 'adoption', ?, ?)""",
            (date_str, f"Adopted: {hypothesis['change']} -> {hypothesis['file']} "
             f"(+{q_after - q_before:.3f})", now))
    else:
        memory.store_failure(
            db, date_str, "autoresearch",
            f"Rejected: {hypothesis['change']}",
            f"Change to {hypothesis['file']} didn't improve quality "
            f"({q_before:.3f} -> {q_after:.3f}). Reason: {hypothesis['reason']}")
    db.commit()
    logger.info("Experiment: %s (adopted=%s, delta=%.4f)",
                hypothesis["change"][:60], adopted, q_after - q_before)


# ── Main ───────────────────────────────────────────────────────────────────

def autoresearch(dry_run: bool = False, user_id: str = "ramsay") -> dict:
    """Run one cycle of self-improvement.

    1. Load quality score + failures + agent performance
    2. Generate 3 hypotheses (Sonnet), pick highest-priority
    3. Branch, apply change, simulate research, evaluate quality
    4. If quality improved: merge to main. Otherwise: rollback + log rejection.
    """
    import memory

    date_str = datetime.now().strftime("%Y-%m-%d")
    t0 = time.monotonic()
    result = {"date": date_str, "user_id": user_id, "dry_run": dry_run,
              "hypothesis": None, "applied": False, "quality_before": None,
              "quality_after": None, "adopted": False, "error": None, "duration_s": 0}

    db = memory.get_db(user_id=user_id)
    use_git = _git_is_repo()
    original_content = None  # for non-git rollback

    try:
        # Load context
        logger.info("Loading context for %s", user_id)
        ctx = _load_quality_context(db)
        q_before = ctx["latest_quality"]["overall_score"] if ctx["latest_quality"] else 0.0
        result["quality_before"] = q_before
        logger.info("Context: quality=%.3f, failures=%d, underperformers=%d",
                     q_before, len(ctx["recent_failures"]), len(ctx["agent_performance"]))

        # Generate hypotheses
        logger.info("Generating hypotheses...")
        hypotheses = _generate_hypotheses(ctx)
        if not hypotheses:
            result["error"] = "No valid hypotheses generated"
            return result

        # Pick best
        hypothesis = _pick_hypothesis(hypotheses)
        result["hypothesis"] = hypothesis
        logger.info("Selected: %s (file: %s)", hypothesis["change"], hypothesis["file"])

        if dry_run:
            result["all_hypotheses"] = hypotheses
            return result

        # Branch
        branch = f"autoresearch-{date_str}"
        if use_git:
            if not _git_is_clean():
                result["error"] = "Working tree not clean"
                return result
            if not _git_branch(branch):
                result["error"] = "Failed to create branch"
                return result
        else:
            logger.warning("No git repo, using in-memory rollback")
            tp = PROJECT_ROOT / hypothesis["file"]
            original_content = tp.read_text() if tp.exists() else None

        # Apply change
        logger.info("Applying change to %s...", hypothesis["file"])
        applied = _apply_change(hypothesis)
        result["applied"] = applied

        if not applied:
            result["error"] = "Failed to apply change"
            if use_git:
                _git_cleanup(branch)
            _log_experiment(db, date_str, hypothesis, False, q_before, q_before)
            return result

        if use_git:
            _git_commit(f"autoresearch: {hypothesis['change'][:60]}\n\n"
                        f"File: {hypothesis['file']}\n"
                        f"Reason: {hypothesis['reason']}")

        # Simulate
        logger.info("Running simulated research...")
        sim = _simulate_research(user_id, date_str)
        q_after = sim.get("overall_score", 0.0) if not sim.get("error") else 0.0
        result["quality_after"] = q_after
        if sim.get("error"):
            result["error"] = f"Simulation failed: {sim['error']}"

        # Decide
        delta = q_after - q_before
        adopted = delta > QUALITY_THRESHOLD and not sim.get("error")
        result["adopted"] = adopted
        logger.info("Quality: %.3f -> %.3f (delta=%+.4f, threshold=%.3f)",
                     q_before, q_after, delta, QUALITY_THRESHOLD)

        if adopted:
            logger.info("ADOPTING (+%.4f)", delta)
            if use_git:
                _git_merge_main(branch)
        else:
            logger.info("REJECTING (%s)",
                        "no improvement" if not sim.get("error") else "sim failed")
            if use_git:
                _git_cleanup(branch)
            elif original_content is not None:
                (PROJECT_ROOT / hypothesis["file"]).write_text(original_content)
                logger.info("Rolled back %s", hypothesis["file"])

        _log_experiment(db, date_str, hypothesis, adopted, q_before, q_after)

    except Exception as e:
        result["error"] = str(e)
        logger.error("Autoresearch failed: %s", e, exc_info=True)
        if use_git:
            try:
                cur = _git(["branch", "--show-current"]).stdout.strip()
                if cur.startswith("autoresearch-"):
                    _git_cleanup(cur)
            except Exception:
                pass
    finally:
        db.close()
        result["duration_s"] = round(time.monotonic() - t0, 1)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Overnight self-improvement")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--user", default="ramsay")
    args = parser.parse_args()

    setup_logging()
    result = autoresearch(dry_run=args.dry_run, user_id=args.user)
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("error") is None else 1)
