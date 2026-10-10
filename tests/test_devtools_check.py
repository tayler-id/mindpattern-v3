"""devtools/check.py runs devtools/checks.json in order and writes a receipt for the commit."""
import json

import pytest

from devtools import check

PASS = ["{python}", "-c", "print('fine')"]
FAIL = ["{python}", "-c", "import sys; print('broken here'); sys.exit(3)"]


def _checks(tmp_path, rows):
    path = tmp_path / "checks.json"
    path.write_text(json.dumps({"checks": rows}))
    return path


def _two(tmp_path):
    return _checks(tmp_path, [{"id": "good", "command": PASS, "about": "passes"},
                              {"id": "bad", "command": FAIL, "about": "fails"}])


def test_the_shipped_checks_load_in_order():
    assert [c.id for c in check.load()] == ["doctor", "config", "layers", "knowledge", "tests"]


@pytest.mark.parametrize("rows,message", [
    ([{"command": PASS, "about": "x"}], "has no id"),
    ([{"id": "a", "command": PASS, "about": "x"}, {"id": "a", "command": PASS, "about": "y"}], "appears twice"),
    ([{"id": "a", "command": "echo hi", "about": "x"}], "non-empty list of strings"),
    ([{"id": "a", "command": PASS}], "needs an about line"),
])
def test_a_bad_checks_file_is_refused(tmp_path, rows, message):
    with pytest.raises(check.CheckFileError, match=message):
        check.load(_checks(tmp_path, rows))


def test_every_check_runs_and_one_failure_fails_the_receipt(tmp_path, capsys):
    receipts = tmp_path / "receipts"
    assert check.main(["--checks", str(_two(tmp_path)), "--receipts", str(receipts)]) == 1
    out = capsys.readouterr().out
    assert "PASS  good" in out and "FAIL  bad" in out and "      broken here" in out
    (receipt,) = receipts.glob("*.json")
    data = json.loads(receipt.read_text())
    assert data["outcome"] == "fail" and data["commit"] == receipt.stem and len(receipt.stem) == 40
    assert [(c["id"], c["passed"], c["exit_code"]) for c in data["checks"]] == [("good", True, 0), ("bad", False, 3)]


def test_only_runs_the_named_checks_and_refuses_an_unknown_one(tmp_path, capsys):
    path, receipts = _two(tmp_path), tmp_path / "receipts"
    assert check.main(["--checks", str(path), "--receipts", str(receipts), "--only", "good"]) == 0
    assert "bad" not in capsys.readouterr().out
    assert check.main(["--checks", str(path), "--receipts", str(receipts), "--only", "nope"]) == 2


def test_list_names_each_check_without_running_it(tmp_path, capsys):
    assert check.main(["--checks", str(_two(tmp_path)), "--list"]) == 0
    assert capsys.readouterr().out.splitlines() == ["good         passes", "bad          fails"]
