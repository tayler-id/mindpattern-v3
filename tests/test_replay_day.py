"""tools/replay_day.py reruns a past day's synthesis in a scratch copy and leaves live state alone.

The test builds a small state root (users.json, memory.db with three findings,
traces.db with the day's trend checkpoint, identity files, an earlier issue)
and puts a fake `claude` on PATH that answers each task the way the real CLI's
stream-json does. The replay drives the real runner, harness, and tracing.
"""
import hashlib
import importlib.util
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("replay_day", PROJECT_ROOT / "tools" / "replay_day.py")
replay_day = importlib.util.module_from_spec(SPEC)
sys.modules["replay_day"] = replay_day
SPEC.loader.exec_module(replay_day)

DAY = "2026-09-30"
NEWSLETTER = (
    "# Placeholder headline\n\n"
    "## Agents ship a release\n\n"
    "Acme shipped version two of its agent runtime with a planner that cut failed tasks in half. "
    "[Acme release notes](https://example.com/acme).\n"
)

FAKE_CLAUDE = '''#!/usr/bin/env python3
import json, os, re, sys
stdin = "" if sys.stdin.isatty() else sys.stdin.read()
args = sys.argv[1:]
prompt = args[args.index("-p") + 1] if "-p" in args and not args[args.index("-p") + 1].startswith("--") else stdin
task = os.environ.get("MINDPATTERN_TASK", "")
if task == "story_deep_dive":
    story = re.search(r"Story id: (\\S+)", prompt).group(1)
    with open(os.environ["MP_EVIDENCE_FILE"], "a") as handle:
        handle.write(json.dumps({"kind": "number", "claim": "Failed tasks fell by half after the release.",
                                 "source_url": "https://example.com/acme", "source_name": "Acme", "story": story}) + "\\n")
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as log:
    log.write(json.dumps({"task": task, "cwd": os.getcwd(),
                          "outbound": os.environ.get("MP_DISABLE_OUTBOUND"),
                          "invoked_by": os.environ.get("CLAUDE_INVOKED_BY"),
                          "evidence_in_prompt": "## Evidence packs" in prompt}) + "\\n")
answers = {
    "synthesis_pass1": json.dumps([{"story_title": "Agents ship a release 0", "agent": "agents-researcher",
                                    "section": "agents", "reason": "biggest release"}]),
    "synthesis_pass2": NEWSLETTER,
    "story_deep_dive": "stored 1 item",
}
print(json.dumps({"type": "system", "subtype": "init", "model": "fake-opus", "session_id": "s-" + task}))
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 1,
                  "result": answers.get(task, "{}"), "total_cost_usd": 0.25,
                  "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100,
                            "cache_read_input_tokens": 1000, "output_tokens": 50}}))
'''.replace("NEWSLETTER", repr(NEWSLETTER))


def _tree_hash(root: Path) -> dict[str, str]:
    """Every file's hash. SQLite's -wal/-shm lock files are left out: opening a WAL
    database at all, even read-only for the snapshot, creates them empty."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file() and not p.name.endswith(("-wal", "-shm"))}


@pytest.fixture
def state_root(tmp_path):
    from memory.db import get_db
    from orchestrator.checkpoint import Checkpoint
    from orchestrator.pipeline import Phase
    from orchestrator.traces_db import init_db

    root = tmp_path / "live"
    data = root / "data" / "ramsay"
    (data / "mindpattern").mkdir(parents=True)
    (root / "users.json").write_text(json.dumps({"users": [{
        "id": "ramsay", "name": "Test", "email": "t@example.com", "newsletter_title": "Test Wire",
        "reply_to": "t@example.com", "vertical": "ai-tech", "active": True}]}))
    for name in ("soul.md", "user.md", "voice.md", "decisions.md"):
        (data / "mindpattern" / name).write_text(f"# {name}\n")
    memory = get_db(db_path=data / "memory.db")
    for index in range(3):
        memory.execute(
            "INSERT INTO findings (run_date, agent, title, summary, importance, source_url, source_name) "
            "VALUES (?, ?, ?, ?, 'high', ?, 'Example')",
            (DAY, "agents-researcher", f"Agents ship a release {index}",
             "Acme shipped version two of its agent runtime.", f"https://example.com/acme{index}"))
    memory.commit()
    memory.close()
    traces = init_db(data / "traces.db")
    traces.execute("INSERT INTO pipeline_runs (id, pipeline_type, status, started_at) "
                   "VALUES ('research-2026-09-30-orig', 'research', 'completed', '2026-09-30 08:00:00')")
    Checkpoint(traces).save("research-2026-09-30-orig", Phase.TREND_SCAN, {"trends": [{"topic": "agents"}]})
    traces.commit()
    traces.close()
    reports = root / "reports" / "ramsay"
    reports.mkdir(parents=True)
    (reports / "2026-09-28.md").write_text("# Sep 28 issue\n\n## Older story\n\nText.\n")
    (reports / f"{DAY}.md").write_text("# What was published on Sep 30\n")
    return root


FAKE_CODEX = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as log:
    log.write(json.dumps({"task": os.environ.get("MINDPATTERN_TASK", ""), "cwd": os.getcwd(),
                          "outbound": os.environ.get("MP_DISABLE_OUTBOUND"),
                          "invoked_by": os.environ.get("CLAUDE_INVOKED_BY")}) + "\\n")
print(json.dumps({"type": "thread.started", "thread_id": "t"}))
print(json.dumps({"type": "item.completed", "item": {"id": "i", "type": "agent_message", "text": '{"edits": []}'}}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 5, "cached_input_tokens": 0, "output_tokens": 3}}))
"""


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(FAKE_CLAUDE)
    script.chmod(0o755)
    codex = bin_dir / "codex"
    codex.write_text(FAKE_CODEX)
    codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ['PATH']}")
    log = tmp_path / "fake-claude.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    return log


def test_replay_writes_a_new_issue_traces_every_call_and_leaves_live_state_alone(state_root, fake_claude, tmp_path):
    before = _tree_hash(state_root)
    out = tmp_path / "out"

    summary = replay_day.replay(day=date(2026, 9, 30), stage="synthesis", out=out, state_root=state_root,
                                timeout=600)

    assert _tree_hash(state_root) == before
    assert Path(summary["result"]["project_root"]).name.startswith("mp-replay-")
    assert summary["live_issue_unchanged"] is True
    assert summary["result"]["trends"] == 1
    assert summary["workspace"]["earlier_issues"] == 1
    assert "Acme shipped version two" in (out / "newsletter.md").read_text()
    assert (out / "original.md").read_text() == "# What was published on Sep 30\n"
    assert {t["task"]: t["calls"] for t in summary["usage"]["tasks"]} == {
        "synthesis_pass1": 1, "story_deep_dive": 1, "synthesis_pass2": 1, "newsletter_editor": 1}
    assert summary["usage"]["cost_usd"] == 0.75
    assert summary["routes"]["synthesis_pass2"]["model"] == "claude-opus-5-5"

    calls = sqlite3.connect(out / "traces" / "traces.db").execute(
        "SELECT task, phase, model, outcome, events_path FROM model_calls ORDER BY task").fetchall()
    assert [(task, phase, model, outcome) for task, phase, model, outcome, _ in calls] == [
        ("newsletter_editor", "synthesis", "gpt-6.1-sol", "success"),
        ("story_deep_dive", "synthesis", "fake-opus", "success"),
        ("synthesis_pass1", "synthesis", "fake-opus", "success"),
        ("synthesis_pass2", "synthesis", "fake-opus", "success"),
    ]
    assert all(Path(path).exists() for *_, path in calls)
    assert json.loads((out / "replay.json").read_text())["date"] == DAY

    model_calls = [json.loads(line) for line in fake_claude.read_text().splitlines()]
    assert [c["task"] for c in model_calls] == ["synthesis_pass1", "story_deep_dive", "synthesis_pass2",
                                                "newsletter_editor"]
    assert [c["task"] for c in model_calls if c.get("evidence_in_prompt")] == ["synthesis_pass2"]
    assert {c["outbound"] for c in model_calls} == {"1"}
    assert {c["invoked_by"] for c in model_calls} == {"mindpattern"}
    assert all(Path(c["cwd"]).name.startswith("mp-replay-") for c in model_calls)


def test_replay_uses_a_models_file_for_a_bakeoff(state_root, fake_claude, tmp_path):
    models = json.loads((PROJECT_ROOT / "config" / "models.json").read_text())
    models["tasks"]["synthesis_pass2"]["model"] = "claude-fable-5-1"
    alternative = tmp_path / "models-fable51.json"
    alternative.write_text(json.dumps(models))

    summary = replay_day.replay(day=date(2026, 9, 30), stage="synthesis", out=tmp_path / "out",
                                state_root=state_root, models=alternative, timeout=600)

    assert summary["routes"]["synthesis_pass2"]["model"] == "claude-fable-5-1"
    assert summary["models_file"] == str(alternative)


def test_replay_refuses_a_used_output_folder(state_root, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "old.md").write_text("x")
    with pytest.raises(replay_day.ReplayError, match="not empty"):
        replay_day.replay(day=date(2026, 9, 30), stage="synthesis", out=out, state_root=state_root)


def test_replay_needs_the_state_roots_users_file(state_root, tmp_path):
    (state_root / "users.json").unlink()
    with pytest.raises(replay_day.ReplayError, match="no users.json"):
        replay_day.replay(day=date(2026, 9, 30), stage="synthesis", out=tmp_path / "out", state_root=state_root)


def test_a_dry_run_replay_makes_no_model_calls(state_root, fake_claude, tmp_path):
    summary = replay_day.replay(day=date(2026, 9, 30), stage="synthesis", out=tmp_path / "out",
                                state_root=state_root, dry_run=True, timeout=600)
    assert summary["usage"] == {"calls": 0}
    assert not fake_claude.exists() or fake_claude.read_text() == ""


FAKE_RESEARCH_CLAUDE = """#!/usr/bin/env python3
import json, os, subprocess, sys
if os.environ.get("MINDPATTERN_TASK") == "research_agent":
    # Store two findings through the real bin/mp on PATH, then hit the turn cap.
    for n in (1, 2):
        finding = {"title": f"Acme releases Runtime {n}.0 with a new planner",
                   "summary": f"Acme released Runtime {n}.0 with a planner that retries failed steps.",
                   "importance": "high", "source_url": f"https://acme.example.com/runtime-{n}",
                   "source_name": "Acme blog"}
        done = subprocess.run(["mp", "finding", "add"], input=json.dumps(finding), capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr
    print("Error: Reached max turns (35)")
    sys.exit(1)
print("{}")
"""


def test_research_replay_keeps_findings_stored_with_mp_through_the_turn_cap(state_root, tmp_path, monkeypatch):
    bin_dir = tmp_path / "research-bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(FAKE_RESEARCH_CLAUDE)
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ['PATH']}")

    summary = replay_day.replay(day=date(2026, 9, 30), stage="research", out=tmp_path / "out",
                                state_root=state_root, agents=["news-researcher"], trend_scan=False, timeout=600)

    assert summary["result"]["agents"] == {"news-researcher": {
        "findings": 2, "stored_with_mp": 2, "classification": "success",
        "duration_ms": summary["result"]["agents"]["news-researcher"]["duration_ms"]}}
