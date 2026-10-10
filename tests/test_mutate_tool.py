"""devtools/mutate.py breaks code, runs its tests, and always restores the file exactly."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("mutate_tool", ROOT / "devtools" / "mutate.py")
mutate = importlib.util.module_from_spec(SPEC)
sys.modules["mutate_tool"] = mutate
SPEC.loader.exec_module(mutate)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "gate.py").write_text("def allowed(n):\n    return n < 10\n\n\ndef unused():\n    return 1\n")
    (tmp_path / "test_gate.py").write_text("from gate import allowed\n\n\ndef test_gate():\n    assert allowed(3) and not allowed(12)\n")
    return tmp_path


def test_a_caught_break_is_red_a_missed_one_is_missed_and_both_restore(project, capsys):
    before = (project / "gate.py").read_bytes()
    plan = project / "plan.json"
    plan.write_text(json.dumps([
        {"file": "gate.py", "old": "n < 10", "new": "True", "tests": ["test_gate.py"]},
        {"file": "gate.py", "old": "return 1", "new": "return 2", "tests": ["test_gate.py"]},
    ]))
    assert mutate.main(["--plan", str(plan), "--cwd", str(project)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("RED     gate.py: 'n < 10' -> 1 failed")
    assert out[1].startswith("MISSED  gate.py: 'return 1' -> 1 passed")
    assert (project / "gate.py").read_bytes() == before


def test_a_mutation_that_does_not_match_exactly_once_is_refused(project, capsys):
    assert mutate.main(["--file", "gate.py", "--old", "return", "--new", "x", "--test", "test_gate.py",
                        "--cwd", str(project)]) == 2
    assert "matches 2 times, needs exactly 1" in capsys.readouterr().out
