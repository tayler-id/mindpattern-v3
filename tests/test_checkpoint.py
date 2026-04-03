"""Tests for orchestrator/checkpoint.py — pipeline resume-on-failure mechanism."""

import sqlite3

import pytest

from orchestrator.checkpoint import Checkpoint
from orchestrator.pipeline import PHASE_ORDER, Phase


@pytest.fixture
def cp():
    """Create a Checkpoint backed by an in-memory SQLite database."""
    conn = sqlite3.connect(":memory:")
    return Checkpoint(conn)


RUN_ID = "daily-2026-04-01-abc123"


class TestSaveAndLoad:
    def test_save_and_load_checkpoint(self, cp):
        """Save a checkpoint, then load it back and verify phase + state_data."""
        cp.save(RUN_ID, Phase.RESEARCH, state_data={"findings": 42})
        phase, data = cp.load(RUN_ID)
        assert phase == Phase.RESEARCH
        assert data == {"findings": 42}

    def test_load_returns_none_when_empty(self, cp):
        """Load on a nonexistent run returns (None, None)."""
        phase, data = cp.load("nonexistent-run")
        assert phase is None
        assert data is None

    def test_save_overwrites_same_phase(self, cp):
        """Saving the same run+phase again updates state_data via upsert."""
        cp.save(RUN_ID, Phase.INIT, state_data={"v": 1})
        cp.save(RUN_ID, Phase.INIT, state_data={"v": 2})
        phase, data = cp.load(RUN_ID)
        assert data == {"v": 2}

    def test_load_returns_latest_checkpoint(self, cp):
        """When multiple phases are saved, load returns the most recent one."""
        # Manually set created_at to ensure deterministic ordering
        # (datetime('now') has second precision, both inserts in same second)
        cp.save(RUN_ID, Phase.INIT)
        cp.conn.execute(
            "UPDATE checkpoints SET created_at = '2026-04-01 00:00:00' "
            "WHERE pipeline_run_id = ? AND phase = ?",
            (RUN_ID, Phase.INIT.value),
        )
        cp.save(RUN_ID, Phase.RESEARCH, state_data={"step": "research"})
        cp.conn.execute(
            "UPDATE checkpoints SET created_at = '2026-04-01 00:01:00' "
            "WHERE pipeline_run_id = ? AND phase = ?",
            (RUN_ID, Phase.RESEARCH.value),
        )
        cp.conn.commit()
        phase, data = cp.load(RUN_ID)
        assert phase == Phase.RESEARCH

    def test_save_with_no_state_data(self, cp):
        """Save without state_data stores None, load returns (phase, None)."""
        cp.save(RUN_ID, Phase.INIT)
        phase, data = cp.load(RUN_ID)
        assert phase == Phase.INIT
        assert data is None


class TestResumeFrom:
    def test_resume_from_returns_next_phase(self, cp):
        """After completing INIT, resume_from should return TREND_SCAN."""
        cp.save(RUN_ID, Phase.INIT)
        next_phase = cp.resume_from(RUN_ID)
        assert next_phase == Phase.TREND_SCAN

    def test_resume_from_mid_pipeline(self, cp):
        """After completing through SYNTHESIS, resume_from should return DELIVER."""
        for phase in [Phase.INIT, Phase.TREND_SCAN, Phase.RESEARCH, Phase.SYNTHESIS]:
            cp.save(RUN_ID, phase)
        next_phase = cp.resume_from(RUN_ID)
        assert next_phase == Phase.DELIVER

    def test_resume_from_returns_none_when_all_complete(self, cp):
        """When all phases including COMPLETED are saved, resume_from returns None."""
        for phase in PHASE_ORDER:
            cp.save(RUN_ID, phase)
        result = cp.resume_from(RUN_ID)
        assert result is None

    def test_resume_from_unknown_phase_returns_init(self, cp):
        """When no checkpoints exist for a run, resume_from returns INIT."""
        result = cp.resume_from("nonexistent-run")
        assert result == Phase.INIT


class TestClear:
    def test_clear_removes_checkpoints(self, cp):
        """After clear, load returns (None, None) and resume_from returns INIT."""
        cp.save(RUN_ID, Phase.INIT)
        cp.save(RUN_ID, Phase.RESEARCH, state_data={"x": 1})
        cp.clear(RUN_ID)
        phase, data = cp.load(RUN_ID)
        assert phase is None
        assert data is None
        assert cp.resume_from(RUN_ID) == Phase.INIT

    def test_clear_only_affects_target_run(self, cp):
        """Clearing one run does not affect checkpoints from another run."""
        other_run = "daily-2026-04-01-other"
        cp.save(RUN_ID, Phase.INIT)
        cp.save(other_run, Phase.RESEARCH)
        cp.clear(RUN_ID)
        phase, _ = cp.load(other_run)
        assert phase == Phase.RESEARCH


class TestGetCompletedPhases:
    def test_get_completed_phases_order(self, cp):
        """get_completed_phases returns phases in the order they were saved."""
        cp.save(RUN_ID, Phase.INIT)
        cp.save(RUN_ID, Phase.TREND_SCAN)
        cp.save(RUN_ID, Phase.RESEARCH)
        completed = cp.get_completed_phases(RUN_ID)
        assert completed == [Phase.INIT, Phase.TREND_SCAN, Phase.RESEARCH]

    def test_get_completed_phases_empty(self, cp):
        """Returns empty list for a nonexistent run."""
        assert cp.get_completed_phases("nonexistent") == []


class TestFindResumableRun:
    def test_find_resumable_run_returns_incomplete(self, cp):
        """Finds a run that has checkpoints but hasn't reached COMPLETED."""
        cp.save(RUN_ID, Phase.INIT, user_id="ramsay")
        cp.save(RUN_ID, Phase.RESEARCH, user_id="ramsay")
        result = cp.find_resumable_run("ramsay", "2026-04-01")
        assert result == RUN_ID

    def test_find_resumable_run_skips_completed(self, cp):
        """Does not return a run that reached COMPLETED."""
        cp.save(RUN_ID, Phase.INIT, user_id="ramsay")
        cp.save(RUN_ID, Phase.COMPLETED, user_id="ramsay")
        result = cp.find_resumable_run("ramsay", "2026-04-01")
        assert result is None

    def test_find_resumable_run_filters_by_user(self, cp):
        """Only returns runs matching the given user_id."""
        cp.save(RUN_ID, Phase.INIT, user_id="ramsay")
        result = cp.find_resumable_run("other-user", "2026-04-01")
        assert result is None

    def test_find_resumable_run_no_runs(self, cp):
        """Returns None when no runs exist for the date."""
        result = cp.find_resumable_run("ramsay", "2099-01-01")
        assert result is None
