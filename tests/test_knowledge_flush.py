"""knowledge/flush.py takes its model from config/models.json like every other caller."""
import runpy
import subprocess
from pathlib import Path

from orchestrator.router import get_route

FLUSH = Path(__file__).resolve().parent.parent / "knowledge" / "flush.py"


def test_flush_extraction_uses_the_knowledge_flush_route(monkeypatch):
    module = runpy.run_path(str(FLUSH), run_name="flush_under_test")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, stdout="nothing worth saving", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    module["_run_claude_extract"]("a short conversation")
    route = get_route("knowledge_flush")
    cmd = seen["cmd"]
    assert cmd[cmd.index("--model") + 1] == route.model
    assert cmd[cmd.index("--max-turns") + 1] == str(route.max_turns)
    assert seen["timeout"] == route.timeout_s
