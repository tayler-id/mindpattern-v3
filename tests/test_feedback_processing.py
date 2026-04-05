"""Tests for feedback processing in the init phase.

Verifies that unprocessed user feedback is parsed via Claude into
preference weight changes, and that mark_processed() is called.

No real Claude CLI calls — subprocess is mocked.
"""

import json
import sqlite3
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from memory.db import _init_schema


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """Create a fresh in-memory database with full schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_schema(conn)
    yield conn
    conn.close()


def _insert_feedback(db, body, subject="Re: Newsletter", from_email="user@example.com", processed=0):
    """Helper to insert a feedback row."""
    now = datetime.now().isoformat()
    db.execute(
        """INSERT INTO user_feedback (email_id, from_email, subject, body, received_at, processed, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (f"eid-{body[:10]}", from_email, subject, body, now, processed, now),
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


# ── Tests ─────────────────────────────────────────────────────────────────


class TestProcessPendingFeedback:
    """Tests for PipelineRunner._process_pending_feedback()."""

    def _make_runner(self, db):
        """Build a minimal PipelineRunner with mocked external deps."""
        with patch("orchestrator.runner.get_traces_db"), \
             patch("orchestrator.runner.create_pipeline_run"), \
             patch("orchestrator.runner.PipelineMonitor"):
            from orchestrator.runner import ResearchPipeline
            runner = ResearchPipeline.__new__(ResearchPipeline)
            runner.db = db
            runner.user_config = {"email": "user@example.com"}
            return runner

    @patch("orchestrator.agents.subprocess.run")
    def test_feedback_parsed_into_preferences(self, mock_subprocess, db):
        """Unprocessed feedback is sent to Claude and preferences are updated."""
        _insert_feedback(db, "I want more coverage on AI safety")
        _insert_feedback(db, "Too much security content, less please")

        llm_response = json.dumps({
            "preferences": [
                {"topic": "ai safety", "weight": 2.0},
                {"topic": "agent security", "weight": -1.5},
            ]
        })
        mock_subprocess.return_value = MagicMock(
            stdout=llm_response, returncode=0
        )

        runner = self._make_runner(db)
        runner._process_pending_feedback()

        # Check preferences were written
        prefs = db.execute(
            "SELECT topic, weight FROM user_preferences ORDER BY topic"
        ).fetchall()
        pref_dict = {r["topic"]: r["weight"] for r in prefs}
        assert pref_dict["ai safety"] == 2.0
        assert pref_dict["agent security"] == -1.5

        # Check feedback marked as processed
        unprocessed = db.execute(
            "SELECT COUNT(*) as c FROM user_feedback WHERE processed = 0"
        ).fetchone()["c"]
        assert unprocessed == 0

    @patch("orchestrator.agents.subprocess.run")
    def test_mark_processed_called_even_for_empty_preferences(self, mock_subprocess, db):
        """Acknowledgment-only feedback still gets marked as processed."""
        _insert_feedback(db, "Great issue, keep it up!")

        llm_response = json.dumps({"preferences": []})
        mock_subprocess.return_value = MagicMock(
            stdout=llm_response, returncode=0
        )

        runner = self._make_runner(db)
        runner._process_pending_feedback()

        # No preferences created
        pref_count = db.execute(
            "SELECT COUNT(*) as c FROM user_preferences"
        ).fetchone()["c"]
        assert pref_count == 0

        # But feedback is still marked processed
        unprocessed = db.execute(
            "SELECT COUNT(*) as c FROM user_feedback WHERE processed = 0"
        ).fetchone()["c"]
        assert unprocessed == 0

    @patch("orchestrator.agents.subprocess.run")
    def test_already_processed_feedback_is_skipped(self, mock_subprocess, db):
        """Feedback with processed=1 is not sent to Claude."""
        _insert_feedback(db, "Old feedback", processed=1)

        runner = self._make_runner(db)
        runner._process_pending_feedback()

        # Claude should not have been called
        mock_subprocess.assert_not_called()

    @patch("orchestrator.agents.subprocess.run")
    def test_no_feedback_does_not_call_claude(self, mock_subprocess, db):
        """When there is no unprocessed feedback, no LLM call is made."""
        runner = self._make_runner(db)
        runner._process_pending_feedback()

        mock_subprocess.assert_not_called()

    @patch("orchestrator.agents.subprocess.run")
    def test_weight_clamped_to_range(self, mock_subprocess, db):
        """Weights outside [-3.0, +3.0] are clamped."""
        _insert_feedback(db, "I absolutely need way more AI coverage")

        llm_response = json.dumps({
            "preferences": [
                {"topic": "ai", "weight": 10.0},
                {"topic": "crypto", "weight": -5.0},
            ]
        })
        mock_subprocess.return_value = MagicMock(
            stdout=llm_response, returncode=0
        )

        runner = self._make_runner(db)
        runner._process_pending_feedback()

        prefs = db.execute(
            "SELECT topic, weight FROM user_preferences ORDER BY topic"
        ).fetchall()
        pref_dict = {r["topic"]: r["weight"] for r in prefs}
        assert pref_dict["ai"] == 3.0
        assert pref_dict["crypto"] == -3.0

    @patch("orchestrator.agents.subprocess.run")
    def test_invalid_json_is_handled_gracefully(self, mock_subprocess, db):
        """If Claude returns invalid JSON, feedback is NOT marked processed."""
        _insert_feedback(db, "More AI please")

        mock_subprocess.return_value = MagicMock(
            stdout="Sorry, I can't parse that.", returncode=0
        )

        runner = self._make_runner(db)
        runner._process_pending_feedback()

        # Feedback should still be unprocessed
        unprocessed = db.execute(
            "SELECT COUNT(*) as c FROM user_feedback WHERE processed = 0"
        ).fetchone()["c"]
        assert unprocessed == 1

    @patch("orchestrator.agents.subprocess.run")
    def test_nonzero_exit_code_is_handled(self, mock_subprocess, db):
        """If Claude exits non-zero, feedback is NOT marked processed."""
        _insert_feedback(db, "More AI please")

        mock_subprocess.return_value = MagicMock(
            stdout="", returncode=1
        )

        runner = self._make_runner(db)
        runner._process_pending_feedback()

        # Feedback should still be unprocessed
        unprocessed = db.execute(
            "SELECT COUNT(*) as c FROM user_feedback WHERE processed = 0"
        ).fetchone()["c"]
        assert unprocessed == 1

    @patch("orchestrator.agents.subprocess.run")
    def test_zero_weight_preferences_are_skipped(self, mock_subprocess, db):
        """Preferences with weight=0.0 are not stored."""
        _insert_feedback(db, "This is better")

        llm_response = json.dumps({
            "preferences": [
                {"topic": "general", "weight": 0.0},
            ]
        })
        mock_subprocess.return_value = MagicMock(
            stdout=llm_response, returncode=0
        )

        runner = self._make_runner(db)
        runner._process_pending_feedback()

        pref_count = db.execute(
            "SELECT COUNT(*) as c FROM user_preferences"
        ).fetchone()["c"]
        assert pref_count == 0

        # Feedback still marked processed
        unprocessed = db.execute(
            "SELECT COUNT(*) as c FROM user_feedback WHERE processed = 0"
        ).fetchone()["c"]
        assert unprocessed == 0

    @patch("orchestrator.agents.subprocess.run")
    def test_json_with_markdown_fences_is_parsed(self, mock_subprocess, db):
        """Claude sometimes wraps JSON in markdown code fences."""
        _insert_feedback(db, "Less funding news")

        fenced = '```json\n{"preferences": [{"topic": "funding", "weight": -1.0}]}\n```'
        mock_subprocess.return_value = MagicMock(
            stdout=fenced, returncode=0
        )

        runner = self._make_runner(db)
        runner._process_pending_feedback()

        prefs = db.execute(
            "SELECT topic, weight FROM user_preferences"
        ).fetchall()
        assert len(prefs) == 1
        assert prefs[0]["topic"] == "funding"
        assert prefs[0]["weight"] == -1.0
