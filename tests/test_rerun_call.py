"""tools/rerun_call.py reruns a traced call's saved prompt with another system prompt."""
import gzip
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import rerun_call  # noqa: E402


@pytest.fixture
def traces(tmp_path):
    prompt = tmp_path / "call.prompt.md.gz"
    with gzip.open(prompt, "wt") as handle:
        handle.write("Write the issue.")
    db = sqlite3.connect(tmp_path / "traces.db")
    db.execute("CREATE TABLE model_calls (id TEXT, task TEXT, prompt_path TEXT)")
    db.execute("INSERT INTO model_calls VALUES ('c1', 'synthesis_pass2', ?), ('c2', 'x', NULL)", (str(prompt),))
    db.commit()
    db.close()
    return tmp_path


def test_a_saved_call_is_rerun_with_the_new_system_prompt(traces, tmp_path, monkeypatch, capsys):
    from orchestrator import agents

    seen = []

    def fake(prompt, task, *, system_prompt_file):
        seen.append((prompt, task, Path(system_prompt_file).name))
        return "## Top 5 stories today\n\n### A story\n\nProse.\n\n- one\n", 0

    monkeypatch.setattr(agents, "run_claude_prompt", fake)
    for name in ("MP_TRACE_ROOT", "MP_DISABLE_OUTBOUND"):
        # setenv, not delenv: delenv of an unset name registers no undo, and main() sets
        # both, which then leaked into every later test and silenced the Slack alert tests.
        monkeypatch.setenv(name, "")
    system = tmp_path / "writer.md"
    system.write_text("You write.")
    out = tmp_path / "out"
    assert rerun_call.main(["--traces", str(traces), "--call", "c1", "--system-prompt", str(system),
                            "--out", str(out), "--runs", "2"]) == 0
    assert seen == [("Write the issue.", "synthesis_pass2", "writer.md")] * 2
    assert (out / "run-2.md").read_text().startswith("## Top 5")
    assert "top | A story" in capsys.readouterr().out
    assert __import__("os").environ["MP_TRACE_ROOT"] == str(out / "traces")


def test_a_call_without_a_saved_prompt_stops_with_a_reason(traces):
    with pytest.raises(SystemExit, match="call c2 has no saved prompt"):
        rerun_call.saved_call(traces, "c2")
