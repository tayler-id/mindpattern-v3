"""Drift control: explicit operator surfaces must stay real goal prompts.

The harness works only as well as the prose agents are handed. This locks
the goal framing, the machine-checkable done condition, and the shared core
block across the Claude command and Codex skill reference without making the
repository-wide AGENTS.md an operator prompt.
"""

import re
from pathlib import Path

V3 = Path(__file__).parent.parent
HANDOFF = V3.parent / "mindpattern-rabbit-hole" / "docs" / "handoff" / "backfill-goal-prompt.md"
COMMAND = V3 / ".claude" / "commands" / "backfill.md"
CODEX_SKILL = V3 / ".agents" / "skills" / "rabbit-hole-backfill" / "references" / "operator-goal.md"

REQUIRED_TOKENS = [
    "/goal",
    "status",
    "claim --size 50",
    "run --claim",
    "--workers 2",
    "--reports-root",
    "remaining_unclaimed",
    "in_progress",
    "ABORTED",
    "failed:*",
    "worktree add",
    "worktree remove",
]


def _core(text: str) -> str:
    match = re.search(r"<!-- backfill-core-start -->(.*)<!-- backfill-core-end -->", text, re.DOTALL)
    assert match, "core block markers missing"
    return match.group(1).strip()


def _surfaces():
    surfaces = [COMMAND, CODEX_SKILL]
    if HANDOFF.exists():  # sibling repo may be absent in CI checkouts
        surfaces.append(HANDOFF)
    return surfaces


def test_prompts_are_goal_prompts_with_machine_checkable_done():
    for path in _surfaces():
        text = path.read_text()
        assert "/goal" in text, path
        # The done condition must require BOTH counters at zero.
        assert "remaining_unclaimed == 0 AND in_progress == 0" in text, path
        # Claimed-but-active work is explicitly not done.
        assert "wait" in text.lower(), path
        for token in REQUIRED_TOKENS:
            assert token in text, f"{path}: missing {token!r}"


def test_prompts_are_not_framed_as_one_batch():
    for path in _surfaces():
        first_lines = "\n".join(path.read_text().splitlines()[:12]).lower()
        assert "run one batch" not in first_lines, path
        assert "until no backfill work remains" in path.read_text(), path


def test_all_surfaces_share_the_same_core_block():
    cores = {path: _core(path.read_text()) for path in _surfaces()}
    values = list(cores.values())
    assert all(core == values[0] for core in values), "prompt surfaces drifted apart"


def test_failed_outcomes_documented_as_normal():
    for path in _surfaces():
        text = path.read_text()
        assert re.search(r"failed:\*.*normal", text, re.DOTALL), path
