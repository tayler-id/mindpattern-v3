"""Tests for orchestrator/checkpoint.py — user_id filtering in find_resumable_run."""

import json
import sqlite3

import pytest

from orchestrator.checkpoint import Checkpoint
from orchestrator.pipeline import Phase


@pytest.fixture
def ckpt(tmp_path):
    """In-memory checkpoint backed by a fresh SQLite connection."""
    conn = sqlite3.connect(":memory:")
    return Checkpoint(conn)


class TestFindResumableRunFiltersByUserId:
    """find_resumable_run must only return runs belonging to the given user_id."""

    def test_find_resumable_run_filters_by_user_id(self, ckpt):
        """Insert runs for two users on the same date.

        Querying for user_a must NOT return user_b's run.
        """
        # user_a has an incomplete run
        ckpt.save("research-2026-03-14-aaa111", Phase.INIT, user_id="user_a")
        ckpt.save("research-2026-03-14-aaa111", Phase.TREND_SCAN, user_id="user_a")

        # user_b also has an incomplete run on the same date
        ckpt.save("research-2026-03-14-bbb222", Phase.INIT, user_id="user_b")

        # Asking for user_a should return user_a's run, NOT user_b's
        result = ckpt.find_resumable_run("user_a", "2026-03-14")
        assert result == "research-2026-03-14-aaa111"

        # Asking for user_b should return user_b's run
        result_b = ckpt.find_resumable_run("user_b", "2026-03-14")
        assert result_b == "research-2026-03-14-bbb222"

    def test_find_resumable_run_returns_none_when_no_runs(self, ckpt):
        """When no runs exist at all, find_resumable_run returns None."""
        result = ckpt.find_resumable_run("ramsay", "2026-03-14")
        assert result is None


class TestCheckpointSaveAndLoad:
    """Tests for save/load round-trip, overwrites, missing runs, and data fidelity."""

    def test_save_and_load_checkpoint(self, ckpt):
        """A saved checkpoint can be loaded back with the correct phase and data."""
        run_id = "research-2026-04-01-abc123"
        ckpt.save(run_id, Phase.RESEARCH, state_data={"articles": 5})

        phase, data = ckpt.load(run_id)
        assert phase == Phase.RESEARCH
        assert data == {"articles": 5}

    def test_checkpoint_overwrites_on_same_date(self, ckpt):
        """Saving the same (run_id, phase) twice overwrites the first checkpoint."""
        run_id = "research-2026-04-01-abc123"
        ckpt.save(run_id, Phase.SYNTHESIS, state_data={"draft": "v1"})
        ckpt.save(run_id, Phase.SYNTHESIS, state_data={"draft": "v2"})

        phase, data = ckpt.load(run_id)
        assert phase == Phase.SYNTHESIS
        assert data == {"draft": "v2"}

    def test_load_nonexistent_returns_none(self, ckpt):
        """Loading a run_id with no checkpoints returns (None, None)."""
        phase, data = ckpt.load("nonexistent-run-000000")
        assert phase is None
        assert data is None

    def test_checkpoint_stores_phase_and_data(self, ckpt):
        """Multiple phases saved for a run are all recorded; get_completed_phases
        returns them in order and each stores its own state_data."""
        run_id = "research-2026-04-01-def456"
        ckpt.save(run_id, Phase.INIT, state_data={"started": True}, user_id="ramsay")
        ckpt.save(run_id, Phase.TREND_SCAN, state_data={"trends": ["AI", "LLM"]}, user_id="ramsay")
        ckpt.save(run_id, Phase.RESEARCH, state_data={"agents": 13}, user_id="ramsay")

        completed = ckpt.get_completed_phases(run_id)
        assert completed == [Phase.INIT, Phase.TREND_SCAN, Phase.RESEARCH]

        # Verify individual phase data via direct DB query
        row = ckpt.conn.execute(
            "SELECT state_data FROM checkpoints WHERE pipeline_run_id = ? AND phase = ?",
            (run_id, Phase.TREND_SCAN.value),
        ).fetchone()
        assert json.loads(row[0]) == {"trends": ["AI", "LLM"]}

    def test_clear_removes_all_checkpoints_for_run(self, ckpt):
        """clear() wipes every checkpoint for the given run_id."""
        run_id = "research-2026-04-01-ghi789"
        ckpt.save(run_id, Phase.INIT)
        ckpt.save(run_id, Phase.TREND_SCAN)

        ckpt.clear(run_id)

        phase, data = ckpt.load(run_id)
        assert phase is None
        assert data is None
        assert ckpt.get_completed_phases(run_id) == []

    def test_resume_from_returns_next_phase(self, ckpt):
        """resume_from returns the phase immediately after the last completed one."""
        run_id = "research-2026-04-01-jkl012"
        ckpt.save(run_id, Phase.INIT)
        ckpt.save(run_id, Phase.TREND_SCAN)

        next_phase = ckpt.resume_from(run_id)
        assert next_phase == Phase.RESEARCH

    def test_resume_from_empty_returns_init(self, ckpt):
        """resume_from with no checkpoints returns Phase.INIT."""
        next_phase = ckpt.resume_from("nonexistent-run-000000")
        assert next_phase == Phase.INIT
