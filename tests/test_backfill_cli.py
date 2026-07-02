"""CLI-level contract for the operator-facing backfill commands.

Function tests lock internals; these lock what an agent actually types:
JSON shapes and exit codes via real subprocesses.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

V3 = Path(__file__).parent.parent

ISSUE_MD = """# Ramsay Research Agent — July 2, 2026

## Top 5 Stories Today

**OpenAI ships agent controls.** [OpenAI](https://openai.com/news/controls)
released new controls. Full body sentence about the release with detail.

---

**Anthropic adds memory tools.** [Anthropic](https://anthropic.com/news/memory)
shipped memory tooling. Another full body sentence with enough detail here.
"""


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "reports"
    (root / "ramsay").mkdir(parents=True)
    (root / "ramsay" / "2026-07-02.md").write_text(ISSUE_MD)
    return root


def _run(args, root):
    return subprocess.run(
        [sys.executable, "-m", "orchestrator.site_backfill", *args, "--reports-root", str(root)],
        capture_output=True,
        text=True,
        cwd=V3,
        env={"PATH": "/usr/bin:/bin", "MP_REPORTS_DIR": str(root), "HOME": str(root.parent)},
        timeout=120,
    )


def test_status_shape_and_exit_code(data_root):
    proc = _run(["status"], data_root)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    for key in ("written", "fallback_artifacts", "in_progress", "in_progress_by_agent",
                "remaining_unclaimed", "notebook"):
        assert key in payload, key
    assert payload["remaining_unclaimed"] == 2


def test_claim_then_status_reflects_ownership(data_root):
    proc = _run(["claim", "--size", "1", "--agent", "cli-test"], data_root)
    assert proc.returncode == 0, proc.stderr
    claim = json.loads(proc.stdout)
    assert claim["claim_id"].endswith("cli-test")
    assert len(claim["slugs"]) == 1

    status = json.loads(_run(["status"], data_root).stdout)
    assert status["in_progress"] == 1
    assert status["in_progress_by_agent"] == {"cli-test": 1}
    assert status["remaining_unclaimed"] == 1


def test_claim_exhausted_pool_exits_3(data_root):
    _run(["claim", "--size", "50", "--agent", "first"], data_root)
    proc = _run(["claim", "--size", "50", "--agent", "second"], data_root)
    assert proc.returncode == 3
    assert json.loads(proc.stdout)["slugs"] == []


def test_run_requires_claim_id(data_root):
    proc = _run(["run"], data_root)
    assert proc.returncode == 2
    assert "--claim is required" in proc.stdout


def test_run_unknown_claim_exits_2(data_root):
    proc = _run(["run", "--claim", "c-00000000-000000-nobody"], data_root)
    assert proc.returncode == 2
    assert "error" in json.loads(proc.stdout.splitlines()[-1])


def test_release_frees_claims(data_root):
    claim = json.loads(_run(["claim", "--size", "2", "--agent", "rel"], data_root).stdout)
    proc = _run(["release", "--claim", claim["claim_id"]], data_root)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["released"] == 2
    assert json.loads(_run(["status"], data_root).stdout)["in_progress"] == 0
