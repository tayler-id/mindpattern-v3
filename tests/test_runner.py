"""Comprehensive tests for orchestrator/runner.py (ResearchPipeline).

Covers: pipeline initialization, all 12 phase handlers, full pipeline run,
error recovery (skippable vs critical phases), and resume from checkpoint.

No real Claude CLI calls or external API calls — all external dependencies
are mocked.
"""

import json
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from orchestrator.pipeline import Phase, PHASE_ORDER, CRITICAL_PHASES

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════════════════
# Shared fixtures
# ═══════════════════════════════════════════════════════════════════════


def _make_memory_db() -> sqlite3.Connection:
    """Create an in-memory SQLite DB with the tables runner expects."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT, weight REAL DEFAULT 1.0,
            effective_weight REAL, email TEXT, active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT, category TEXT, lesson TEXT, details TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT, agent TEXT, title TEXT, summary TEXT,
            importance TEXT DEFAULT 'medium', category TEXT,
            source_url TEXT, source_name TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT, topic_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT, run_date TEXT, findings_count INTEGER
        );
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT, name TEXT, quality TEXT, last_seen TEXT
        );
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_a TEXT, relationship TEXT, entity_b TEXT,
            entity_a_type TEXT, entity_b_type TEXT, finding_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS engagements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, platform TEXT, engagement_type TEXT,
            target_post_url TEXT, target_author TEXT,
            target_author_id TEXT, target_content TEXT,
            our_reply TEXT, status TEXT DEFAULT 'drafted',
            finding_id INTEGER, created_at TEXT, posted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline TEXT, signal_type TEXT, topic TEXT,
            strength REAL, evidence TEXT, run_date TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    db.commit()
    return db


def _make_traces_conn() -> sqlite3.Connection:
    """Create an in-memory traces DB with all tables needed by runner."""
    from orchestrator.traces_db import init_db
    # init_db expects a Path — use a temp file that we immediately connect in-memory
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id TEXT PRIMARY KEY, pipeline_type TEXT, status TEXT,
            started_at TEXT, completed_at TEXT, trigger TEXT, error TEXT, metadata TEXT
        );
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY, pipeline_run_id TEXT, agent_name TEXT,
            status TEXT, started_at TEXT, completed_at TEXT,
            input_tokens INTEGER, output_tokens INTEGER, latency_ms INTEGER,
            prompt_version TEXT, quality_score REAL, error TEXT, output TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_run_id TEXT, event_type TEXT, payload TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS pipeline_phases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_run_id TEXT NOT NULL, phase_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running', started_at TEXT NOT NULL,
            completed_at TEXT, tokens_used INTEGER, cost REAL, error TEXT
        );
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT, git_hash TEXT, captured_at TEXT, file_path TEXT,
            UNIQUE(agent_name, git_hash)
        );
        CREATE TABLE IF NOT EXISTS daily_metrics (
            date TEXT, metric_name TEXT, metric_value REAL,
            PRIMARY KEY (date, metric_name)
        );
        CREATE TABLE IF NOT EXISTS quality_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_run_id TEXT, prompt_version_id INTEGER,
            dimension TEXT, score REAL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS evolution_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL, agents_affected TEXT NOT NULL,
            reasoning TEXT, date TEXT NOT NULL, metadata TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS trace_spans (
            id TEXT PRIMARY KEY, agent_run_id TEXT, parent_span_id TEXT,
            span_type TEXT, name TEXT, input TEXT, output TEXT,
            started_at TEXT, duration_ms INTEGER
        );
        CREATE TABLE IF NOT EXISTS proof_packages (
            id TEXT PRIMARY KEY, pipeline_run_id TEXT, topic TEXT,
            status TEXT, quality_score REAL, creative_brief TEXT,
            post_text TEXT, art_path TEXT, sources TEXT, post_results TEXT,
            reviewer_notes TEXT, created_at TEXT, reviewed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS agent_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL, run_date TEXT NOT NULL,
            findings_count INTEGER DEFAULT 0, tokens_used INTEGER DEFAULT 0,
            cost REAL DEFAULT 0.0, duration_ms INTEGER DEFAULT 0, model_used TEXT
        );
        CREATE TABLE IF NOT EXISTS cost_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL, phase TEXT NOT NULL, model TEXT NOT NULL,
            input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL, alert_type TEXT NOT NULL,
            message TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'warning',
            acknowledged INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS quality_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL, dimension TEXT NOT NULL,
            score REAL NOT NULL, delta_from_avg REAL
        );
        CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_run_id TEXT NOT NULL, phase TEXT NOT NULL,
            state_data TEXT,
            user_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(pipeline_run_id, phase)
        );
        CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON checkpoints(pipeline_run_id);
        CREATE INDEX IF NOT EXISTS idx_checkpoints_user ON checkpoints(user_id);
    """)
    conn.commit()
    return conn


# A stub AgentResult used by multiple tests
@dataclass
class _StubAgentResult:
    agent_name: str
    findings: list = field(default_factory=list)
    raw_output: str = ""
    exit_code: int = 0
    duration_ms: int = 1000
    killed_by_timeout: bool = False
    error: str | None = None


# Shared patches that every ResearchPipeline.__init__ needs
_INIT_PATCHES = {
    "orchestrator.runner.agent_dispatch.load_user_config": lambda uid: {
        "id": uid,
        "email": "test@example.com",
        "newsletter_title": "Test Newsletter",
        "phone": "+15551234567",
    },
    "orchestrator.runner.agent_dispatch.load_global_config": lambda: {
        "model": "sonnet",
        "max_turns": 10,
        "email": "test@example.com",
        "report_dir": "reports",
        "memory_db": "data/test/memory.db",
    },
    "orchestrator.runner.agent_dispatch.set_pipeline_date": lambda d: None,
}


@pytest.fixture()
def memory_db():
    """In-memory SQLite database mimicking the memory module schema."""
    db = _make_memory_db()
    yield db
    db.close()


@pytest.fixture()
def traces_conn():
    """In-memory traces DB with all required tables."""
    conn = _make_traces_conn()
    yield conn
    conn.close()


@pytest.fixture()
def pipeline(memory_db, traces_conn):
    """Build a fully mocked ResearchPipeline instance."""
    with (
        patch("orchestrator.runner.agent_dispatch.load_user_config",
              return_value={"id": "testuser", "email": "test@example.com",
                            "newsletter_title": "Test Newsletter",
                            "phone": "+15551234567"}),
        patch("orchestrator.runner.agent_dispatch.load_global_config",
              return_value={"model": "sonnet", "max_turns": 10,
                            "email": "test@example.com",
                            "report_dir": "reports",
                            "memory_db": "data/test/memory.db"}),
        patch("orchestrator.runner.agent_dispatch.set_pipeline_date"),
        patch("orchestrator.runner.memory.get_db", return_value=memory_db),
        patch("orchestrator.runner.get_traces_db", return_value=traces_conn),
        patch("orchestrator.runner.create_pipeline_run", return_value="test-run-001"),
    ):
        from orchestrator.runner import ResearchPipeline
        p = ResearchPipeline.__new__(ResearchPipeline)
        p.user_id = "testuser"
        p.date_str = "2026-03-19"
        p.user_config = {
            "id": "testuser", "email": "test@example.com",
            "newsletter_title": "Test Newsletter",
            "phone": "+15551234567",
        }
        p.global_config = {"model": "sonnet", "max_turns": 10,
                           "email": "test@example.com",
                           "report_dir": "reports",
                           "memory_db": "data/test/memory.db"}
        p.db = memory_db
        p.trends = []
        p.agent_results = []
        p.newsletter_text = ""
        p.newsletter_eval = {}
        p.social_result = {}
        p.traces_conn = traces_conn
        # Insert a pipeline_runs row so FK references work
        traces_conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_type, status, started_at, trigger) "
            "VALUES (?, ?, ?, datetime('now'), ?)",
            ("test-run-001", "research", "running", "manual"),
        )
        traces_conn.commit()

        from orchestrator.checkpoint import Checkpoint
        from orchestrator.observability import PipelineMonitor
        from orchestrator.pipeline import PipelineRun

        p.checkpoint = Checkpoint(traces_conn)
        p.monitor = PipelineMonitor(traces_conn)
        p.pipeline = PipelineRun("research", "testuser", "2026-03-19")
        p.pipeline.run_id = "test-run-001"
        p.traces_run_id = "test-run-001"
        p.prompt_tracker = None
        p.prompt_changes = {}

        yield p


# ═══════════════════════════════════════════════════════════════════════
# 1. Pipeline initialization
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineInit:
    """Verify ResearchPipeline.__init__ loads config, connects DB, and
    sets up all expected attributes."""

    @patch("orchestrator.runner.create_pipeline_run", return_value="init-run-001")
    @patch("orchestrator.runner.get_traces_db")
    @patch("orchestrator.runner.memory.get_db")
    @patch("orchestrator.runner.agent_dispatch.set_pipeline_date")
    @patch("orchestrator.runner.agent_dispatch.load_global_config",
           return_value={"model": "sonnet", "max_turns": 10, "email": "a@b.com",
                         "report_dir": "reports", "memory_db": "data/test/memory.db"})
    @patch("orchestrator.runner.agent_dispatch.load_user_config",
           return_value={"id": "testuser", "email": "a@b.com",
                         "newsletter_title": "Test", "phone": "+1"})
    def test_init_sets_attributes(self, mock_user, mock_global, mock_date,
                                  mock_mem_db, mock_traces, mock_create):
        mem_db = _make_memory_db()
        traces = _make_traces_conn()
        mock_mem_db.return_value = mem_db
        mock_traces.return_value = traces

        from orchestrator.runner import ResearchPipeline
        p = ResearchPipeline("testuser", "2026-03-19")

        assert p.user_id == "testuser"
        assert p.date_str == "2026-03-19"
        assert p.user_config["email"] == "a@b.com"
        assert p.global_config["model"] == "sonnet"
        assert p.db is mem_db
        assert p.traces_conn is traces
        assert p.trends == []
        assert p.agent_results == []
        assert p.newsletter_text == ""
        assert p.newsletter_eval == {}
        assert p.social_result == {}
        mock_date.assert_called_once_with("2026-03-19")
        mock_create.assert_called_once()

        mem_db.close()
        traces.close()

    @patch("orchestrator.runner.create_pipeline_run", return_value="init-run-002")
    @patch("orchestrator.runner.get_traces_db")
    @patch("orchestrator.runner.memory.get_db")
    @patch("orchestrator.runner.agent_dispatch.set_pipeline_date")
    @patch("orchestrator.runner.agent_dispatch.load_global_config",
           return_value={"model": "sonnet", "max_turns": 10, "email": "a@b.com",
                         "report_dir": "reports", "memory_db": "data/test/memory.db"})
    @patch("orchestrator.runner.agent_dispatch.load_user_config",
           return_value={"id": "testuser", "email": "a@b.com",
                         "newsletter_title": "Test", "phone": "+1"})
    def test_init_defaults_date_to_today(self, mock_user, mock_global, mock_date,
                                         mock_mem_db, mock_traces, mock_create):
        mem_db = _make_memory_db()
        traces = _make_traces_conn()
        mock_mem_db.return_value = mem_db
        mock_traces.return_value = traces

        from orchestrator.runner import ResearchPipeline
        p = ResearchPipeline("testuser")

        # Should be today's date in YYYY-MM-DD format
        from datetime import datetime
        assert p.date_str == datetime.now().strftime("%Y-%m-%d")

        mem_db.close()
        traces.close()

    def test_phase_handler_map_has_all_non_terminal_phases(self, pipeline):
        """Every non-terminal, non-COMPLETED/FAILED phase has a handler.
        EVOLVE is intentionally disabled (see reports/audit/evolve.md)."""
        expected_phases = {
            Phase.INIT, Phase.TREND_SCAN, Phase.RESEARCH, Phase.SYNTHESIS,
            Phase.DELIVER, Phase.LEARN, Phase.SOCIAL, Phase.ENGAGEMENT,
            # Phase.EVOLVE disabled: zero measurable improvement, 5-8 min waste/run
            Phase.IDENTITY, Phase.MIRROR, Phase.SYNC,
        }
        for phase in expected_phases:
            handler = pipeline._get_phase_handler(phase)
            assert handler is not None, f"No handler for phase {phase.value}"

    def test_phase_handler_returns_none_for_completed(self, pipeline):
        assert pipeline._get_phase_handler(Phase.COMPLETED) is None

    def test_phase_handler_returns_none_for_failed(self, pipeline):
        assert pipeline._get_phase_handler(Phase.FAILED) is None


# ═══════════════════════════════════════════════════════════════════════
# 2. Individual phase handler tests
# ═══════════════════════════════════════════════════════════════════════


class TestPhaseInit:
    """_phase_init: loads preferences, feedback, failures, prompt tracking."""

    def _mock_tracker(self, changes=None):
        """Build a mock PromptTracker class that returns the given changes."""
        mock_instance = MagicMock()
        mock_instance.scan_for_changes.return_value = changes or {}
        return MagicMock(return_value=mock_instance), mock_instance

    @patch("orchestrator.runner.memory.recent_failures", return_value=[])
    @patch("orchestrator.runner.memory.list_preferences", return_value=[
        {"topic": "AI", "weight": 1.0, "effective_weight": 1.0}
    ])
    def test_happy_path(self, mock_prefs, mock_failures, pipeline):
        tracker_cls, tracker_inst = self._mock_tracker()

        with (
            patch.object(pipeline, "_keychain_lookup", return_value=None),
            patch("orchestrator.runner.PromptTracker", tracker_cls),
        ):
            result = pipeline._phase_init()

        assert result["preferences_count"] == 1
        assert result["failures_loaded"] == 0
        assert result["prompt_changes"] == 0

    @patch("orchestrator.runner.memory.recent_failures", return_value=[
        {"category": "quality_drop", "lesson": "too short"}
    ])
    @patch("orchestrator.runner.memory.list_preferences", return_value=[])
    def test_loads_failures(self, mock_prefs, mock_failures, pipeline):
        tracker_cls, tracker_inst = self._mock_tracker()

        with (
            patch.object(pipeline, "_keychain_lookup", return_value=None),
            patch("orchestrator.runner.PromptTracker", tracker_cls),
        ):
            result = pipeline._phase_init()

        assert result["failures_loaded"] == 1

    @patch("orchestrator.runner.memory.recent_failures", return_value=[])
    @patch("orchestrator.runner.memory.list_preferences", return_value=[])
    def test_feedback_failure_is_noncritical(self, mock_prefs, mock_failures, pipeline):
        """If feedback fetch fails, init still completes."""
        tracker_cls, tracker_inst = self._mock_tracker()

        with (
            patch.object(pipeline, "_keychain_lookup", return_value="fake-key"),
            patch("orchestrator.runner.memory.fetch_feedback",
                  side_effect=Exception("Resend API down")),
            patch("orchestrator.runner.PromptTracker", tracker_cls),
        ):
            result = pipeline._phase_init()

        # Should still return successfully
        assert "preferences_count" in result

    @patch("orchestrator.runner.memory.recent_failures", return_value=[])
    @patch("orchestrator.runner.memory.list_preferences", return_value=[])
    def test_prompt_changes_detected(self, mock_prefs, mock_failures, pipeline):
        changes = {
            "agents/researcher.md": {
                "changed": True, "old_hash": "aaa", "new_hash": "bbb",
            },
            "agents/scanner.md": {
                "changed": False, "old_hash": "ccc", "new_hash": "ccc",
            },
        }
        tracker_cls, tracker_inst = self._mock_tracker(changes)

        with (
            patch.object(pipeline, "_keychain_lookup", return_value=None),
            patch("orchestrator.runner.PromptTracker", tracker_cls),
        ):
            result = pipeline._phase_init()

        assert result["prompt_changes"] == 1
        tracker_inst.record_version.assert_called_once_with("agents/researcher.md")


class TestPhaseTrendScan:
    """_phase_trend_scan: calls Claude CLI, parses trend JSON."""

    def test_happy_path_json_array(self, pipeline):
        trends = [{"topic": "GPT-5"}, {"topic": "Quantum"}]
        with patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                    return_value=(json.dumps(trends), 0)):
            result = pipeline._phase_trend_scan()

        assert result["trends"] == trends
        assert pipeline.trends == trends

    def test_json_object_with_topics_key(self, pipeline):
        data = {"topics": [{"topic": "AI Act"}, {"topic": "LLMs"}]}
        with patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                    return_value=(json.dumps(data), 0)):
            result = pipeline._phase_trend_scan()

        assert len(result["trends"]) == 2

    def test_json_embedded_in_text(self, pipeline):
        output = 'Here are the trends:\n[{"topic": "Rust"}]\nEnd.'
        with patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                    return_value=(output, 0)):
            result = pipeline._phase_trend_scan()

        assert len(result["trends"]) == 1
        assert result["trends"][0]["topic"] == "Rust"

    def test_no_output_returns_empty(self, pipeline):
        with patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                    return_value=("", 0)):
            result = pipeline._phase_trend_scan()

        assert result["trends"] == []

    def test_nonzero_exit_code_returns_empty(self, pipeline):
        with patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                    return_value=("some text", 1)):
            result = pipeline._phase_trend_scan()

        assert result["trends"] == []

    def test_invalid_json_returns_empty(self, pipeline):
        with patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                    return_value=("not json at all", 0)):
            result = pipeline._phase_trend_scan()

        assert result["trends"] == []


class TestPhaseResearch:
    """_phase_research: dispatches agents, stores findings, dedup."""

    def _make_agent_result(self, agent_name="test-agent", findings=None, error=None):
        return _StubAgentResult(
            agent_name=agent_name,
            findings=findings or [],
            error=error,
        )

    @patch("orchestrator.runner.memory.log_agent_run")
    @patch("orchestrator.runner.memory.store_source")
    @patch("orchestrator.runner.memory.store_finding")
    @patch("orchestrator.runner.memory.search_findings", return_value=[])
    @patch("orchestrator.runner.memory.get_signal_context", return_value="")
    @patch("orchestrator.runner.memory.get_context", return_value="some context")
    @patch("orchestrator.runner.memory.list_claims", return_value=[])
    @patch("orchestrator.runner.memory.clear_claims")
    @patch("orchestrator.runner.agent_dispatch.dispatch_research_agents")
    def test_happy_path(self, mock_dispatch, mock_clear, mock_claims,
                        mock_ctx, mock_signal, mock_search, mock_store,
                        mock_source, mock_log, pipeline):
        findings = [
            {"title": "Finding 1", "summary": "Summary 1", "importance": "high",
             "source_url": "https://example.com/1", "source_name": "Example"},
        ]
        mock_dispatch.return_value = [self._make_agent_result(findings=findings)]

        result = pipeline._phase_research()

        assert result["agents_dispatched"] == 1
        assert result["agents_succeeded"] == 1
        assert result["findings_stored"] == 1
        mock_store.assert_called_once()
        mock_source.assert_called_once()

    @patch("orchestrator.runner.memory.log_agent_run")
    @patch("orchestrator.runner.memory.store_finding")
    @patch("orchestrator.runner.memory.search_findings", return_value=[
        {"similarity": 0.97, "title": "Existing finding"}
    ])
    @patch("orchestrator.runner.memory.get_signal_context", return_value="")
    @patch("orchestrator.runner.memory.get_context", return_value="")
    @patch("orchestrator.runner.memory.list_claims", return_value=[])
    @patch("orchestrator.runner.memory.clear_claims")
    @patch("orchestrator.runner.agent_dispatch.dispatch_research_agents")
    def test_dedup_skips_similar_findings(self, mock_dispatch, mock_clear,
                                          mock_claims, mock_ctx, mock_signal,
                                          mock_search, mock_store, mock_log,
                                          pipeline):
        findings = [
            {"title": "Dup Finding", "summary": "Same as existing",
             "importance": "medium"},
        ]
        mock_dispatch.return_value = [self._make_agent_result(findings=findings)]

        # Should raise because 0 findings stored (dedup filtered all)
        with pytest.raises(RuntimeError, match="Zero findings stored"):
            pipeline._phase_research()

        # store_finding should NOT have been called
        mock_store.assert_not_called()

    @patch("orchestrator.runner.memory.get_signal_context", return_value="")
    @patch("orchestrator.runner.memory.get_context", return_value="")
    @patch("orchestrator.runner.memory.list_claims", return_value=[])
    @patch("orchestrator.runner.memory.clear_claims")
    @patch("orchestrator.runner.agent_dispatch.dispatch_research_agents")
    def test_zero_findings_raises(self, mock_dispatch, mock_clear,
                                   mock_claims, mock_ctx, mock_signal, pipeline):
        # All agents failed
        mock_dispatch.return_value = [
            self._make_agent_result(error="timeout", findings=[])
        ]

        with pytest.raises(RuntimeError, match="Zero findings stored"):
            pipeline._phase_research()


class TestPhaseSynthesis:
    """_phase_synthesis: two-pass synthesis and newsletter evaluation."""

    def _seed_findings(self, db, date_str, count=3):
        for i in range(count):
            db.execute(
                "INSERT INTO findings (run_date, agent, title, summary, importance, source_url, source_name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (date_str, f"agent-{i}", f"Title {i}", f"Summary {i}",
                 "high" if i == 0 else "medium",
                 f"https://example.com/{i}", f"Source {i}"),
            )
        db.commit()

    @patch("orchestrator.runner.memory.recent_failures", return_value=[])
    @patch("orchestrator.runner.memory.list_preferences", return_value=[])
    @patch("orchestrator.runner.agent_dispatch.run_claude_prompt")
    def test_happy_path(self, mock_claude, mock_prefs, mock_failures, pipeline, tmp_path):
        self._seed_findings(pipeline.db, pipeline.date_str)

        # pass1 returns selection, pass2 returns newsletter
        mock_claude.side_effect = [
            ("Selected stories: 1, 2, 3", 0),  # pass1
            ("# Newsletter\n\nGreat content here.\n" + ("word " * 3500), 0),  # pass2
        ]

        # Patch report_dir so it writes to tmp_path
        with patch("orchestrator.runner.PROJECT_ROOT", tmp_path):
            report_dir = tmp_path / "reports" / "testuser"
            report_dir.mkdir(parents=True, exist_ok=True)

            with patch("orchestrator.runner.NewsletterEvaluator") as mock_eval_cls:
                mock_evaluator = MagicMock()
                mock_evaluator.evaluate.return_value = {
                    "overall": 0.85, "coverage": 0.9, "dedup": 0.95,
                    "sources": 0.8,
                }
                mock_eval_cls.return_value = mock_evaluator

                result = pipeline._phase_synthesis()

        assert result["word_count"] > 0
        assert "report_path" in result
        assert pipeline.newsletter_text != ""

    @patch("orchestrator.runner.memory.list_preferences", return_value=[])
    @patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
           return_value=("", 1))
    def test_no_findings_raises(self, mock_claude, mock_prefs, pipeline):
        # No findings in the DB
        with pytest.raises(RuntimeError, match="No findings available"):
            pipeline._phase_synthesis()

    @patch("orchestrator.runner.memory.recent_failures", return_value=[])
    @patch("orchestrator.runner.memory.list_preferences", return_value=[])
    @patch("orchestrator.runner.agent_dispatch.run_claude_prompt")
    def test_pass2_failure_raises(self, mock_claude, mock_prefs, mock_failures,
                                   pipeline, tmp_path):
        self._seed_findings(pipeline.db, pipeline.date_str)

        mock_claude.side_effect = [
            ("Selected stories", 0),  # pass1 OK
            ("", 1),                  # pass2 attempt 1 fails
            ("", 1),                  # pass2 attempt 2 fails
            ("", 1),                  # pass2 attempt 3 fails
        ]

        with patch("orchestrator.runner.PROJECT_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="Synthesis pass 2 failed"):
                pipeline._phase_synthesis()


class TestPhaseDeliver:
    """_phase_deliver: validates report, appends footer, sends newsletter."""

    @patch("orchestrator.runner.memory.get_feedback_footer", return_value="---\nFeedback footer")
    def test_happy_path(self, mock_footer, pipeline, tmp_path):
        # Set up report file
        with patch("orchestrator.runner.PROJECT_ROOT", tmp_path):
            report_dir = tmp_path / "reports" / "testuser"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"{pipeline.date_str}.md"
            report_path.write_text("# Newsletter\n\nContent here.")

            mock_validate = MagicMock(return_value={"final_bytes": 100})
            mock_send = MagicMock(return_value={
                "success": True, "resend_id": "re_abc123"
            })

            with (
                patch("orchestrator.newsletter.send_newsletter", mock_send),
                patch("orchestrator.newsletter.validate_report", mock_validate),
            ):
                result = pipeline._phase_deliver()

        assert result["success"] is True
        assert result["resend_id"] == "re_abc123"

    @patch("orchestrator.runner.memory.get_feedback_footer", return_value="")
    def test_send_failure_returns_error(self, mock_footer, pipeline, tmp_path):
        with patch("orchestrator.runner.PROJECT_ROOT", tmp_path):
            report_dir = tmp_path / "reports" / "testuser"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"{pipeline.date_str}.md"
            report_path.write_text("# Newsletter\n\nContent.")

            with (
                patch("orchestrator.newsletter.send_newsletter",
                      return_value={"success": False, "error": "API error"}),
                patch("orchestrator.newsletter.validate_report",
                      return_value={"final_bytes": 50}),
            ):
                result = pipeline._phase_deliver()

        assert result["success"] is False

    @patch("orchestrator.runner.memory.get_feedback_footer", return_value="---\nFeedback footer")
    def test_broadcasts_to_subscribers(self, mock_footer, pipeline, tmp_path):
        """When user has broadcast_audience, broadcast is called with clean content."""
        pipeline.user_config["broadcast_audience"] = "resend-audience-id"

        with patch("orchestrator.runner.PROJECT_ROOT", tmp_path):
            report_dir = tmp_path / "reports" / "testuser"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"{pipeline.date_str}.md"
            report_path.write_text("# Newsletter\n\nContent here.")

            mock_send = MagicMock(return_value={"success": True, "resend_id": "re_abc"})
            mock_broadcast = MagicMock(return_value={
                "sent_count": 2, "failed_count": 0, "skipped_count": 1, "errors": []
            })

            with (
                patch("orchestrator.newsletter.send_newsletter", mock_send),
                patch("orchestrator.newsletter.validate_report",
                      MagicMock(return_value={"final_bytes": 100})),
                patch("orchestrator.newsletter.broadcast_to_subscribers", mock_broadcast),
            ):
                result = pipeline._phase_deliver()

        assert result["success"] is True
        mock_broadcast.assert_called_once()
        # Broadcast content should NOT contain feedback footer
        broadcast_content = mock_broadcast.call_args.args[0]
        assert "Feedback footer" not in broadcast_content
        assert "# Newsletter" in broadcast_content

    @patch("orchestrator.runner.memory.get_feedback_footer", return_value="")
    def test_broadcasts_even_if_personal_fails(self, mock_footer, pipeline, tmp_path):
        """Broadcast runs regardless of personal send result."""
        pipeline.user_config["broadcast_audience"] = "resend-audience-id"

        with patch("orchestrator.runner.PROJECT_ROOT", tmp_path):
            report_dir = tmp_path / "reports" / "testuser"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"{pipeline.date_str}.md"
            report_path.write_text("# Newsletter\n\nContent.")

            mock_send = MagicMock(return_value={"success": False, "error": "API error"})
            mock_broadcast = MagicMock(return_value={
                "sent_count": 1, "failed_count": 0, "skipped_count": 0, "errors": []
            })

            with (
                patch("orchestrator.newsletter.send_newsletter", mock_send),
                patch("orchestrator.newsletter.validate_report",
                      MagicMock(return_value={"final_bytes": 50})),
                patch("orchestrator.newsletter.broadcast_to_subscribers", mock_broadcast),
            ):
                result = pipeline._phase_deliver()

        assert result["success"] is False
        mock_broadcast.assert_called_once()

    @patch("orchestrator.runner.memory.get_feedback_footer", return_value="")
    def test_skips_broadcast_without_config(self, mock_footer, pipeline, tmp_path):
        """Without broadcast_audience in user config, no broadcast happens."""
        # Ensure no broadcast_audience key
        pipeline.user_config.pop("broadcast_audience", None)

        with patch("orchestrator.runner.PROJECT_ROOT", tmp_path):
            report_dir = tmp_path / "reports" / "testuser"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"{pipeline.date_str}.md"
            report_path.write_text("# Newsletter\n\nContent.")

            mock_send = MagicMock(return_value={"success": True, "resend_id": "re_abc"})
            mock_broadcast = MagicMock()

            with (
                patch("orchestrator.newsletter.send_newsletter", mock_send),
                patch("orchestrator.newsletter.validate_report",
                      MagicMock(return_value={"final_bytes": 50})),
                patch("orchestrator.newsletter.broadcast_to_subscribers", mock_broadcast),
            ):
                result = pipeline._phase_deliver()

        assert result["success"] is True
        mock_broadcast.assert_not_called()


class TestPhaseLearn:
    """_phase_learn: evaluates quality, consolidates memory, prompt regression."""

    @patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
           return_value=("# Learnings\nUpdated content.", 0))
    @patch("orchestrator.runner.memory.get_stats", return_value={"findings": 100})
    @patch("orchestrator.runner.memory.prune", return_value={"pruned": 5})
    @patch("orchestrator.runner.memory.promote", return_value={"promoted": 2})
    @patch("orchestrator.runner.memory.consolidate", return_value={"merged": 3})
    @patch("orchestrator.runner.memory.evaluate_run",
           return_value={"overall_score": 0.85})
    def test_happy_path(self, mock_eval, mock_consolidate, mock_promote,
                        mock_prune, mock_stats, mock_claude, pipeline, tmp_path):
        with patch("orchestrator.runner.PROJECT_ROOT", tmp_path):
            data_dir = tmp_path / "data" / "testuser"
            data_dir.mkdir(parents=True, exist_ok=True)

            result = pipeline._phase_learn()

        assert result["quality"]["overall_score"] == 0.85
        assert result["consolidated"]["merged"] == 3
        assert result["promoted"]["promoted"] == 2
        assert result["pruned"]["pruned"] == 5

    @patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
           return_value=("", 0))
    @patch("orchestrator.runner.memory.get_stats", return_value={})
    @patch("orchestrator.runner.memory.prune", return_value={})
    @patch("orchestrator.runner.memory.promote", return_value={})
    @patch("orchestrator.runner.memory.consolidate", return_value={})
    @patch("orchestrator.runner.memory.store_failure")
    @patch("orchestrator.runner.memory.evaluate_run",
           return_value={"overall_score": 0.5, "warning": "Quality dropped"})
    def test_quality_warning_stores_failure(self, mock_eval, mock_store_failure,
                                            mock_consolidate, mock_promote,
                                            mock_prune, mock_stats,
                                            mock_claude, pipeline, tmp_path):
        with patch("orchestrator.runner.PROJECT_ROOT", tmp_path):
            data_dir = tmp_path / "data" / "testuser"
            data_dir.mkdir(parents=True, exist_ok=True)
            pipeline._phase_learn()

        mock_store_failure.assert_called_once()

    @patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
           return_value=("", 0))
    @patch("orchestrator.runner.memory.get_stats", return_value={})
    @patch("orchestrator.runner.memory.prune", return_value={})
    @patch("orchestrator.runner.memory.promote", return_value={})
    @patch("orchestrator.runner.memory.consolidate", return_value={})
    @patch("orchestrator.runner.memory.evaluate_run",
           return_value={"overall_score": 0.85})
    def test_entity_relationships_stored(self, mock_eval, mock_consolidate,
                                          mock_promote, mock_prune,
                                          mock_stats, mock_claude,
                                          pipeline, tmp_path):
        # Insert a high-importance finding
        pipeline.db.execute(
            "INSERT INTO findings (run_date, agent, title, summary, importance, source_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pipeline.date_str, "agent-1", "AI Breakthrough", "Details", "high", "TechCrunch"),
        )
        pipeline.db.commit()

        with (
            patch("orchestrator.runner.PROJECT_ROOT", tmp_path),
            patch("orchestrator.runner.memory.store_relationship") as mock_rel,
        ):
            data_dir = tmp_path / "data" / "testuser"
            data_dir.mkdir(parents=True, exist_ok=True)
            result = pipeline._phase_learn()

        assert result["entity_relationships_stored"] == 1
        mock_rel.assert_called_once()


class TestPhaseSocial:
    """_phase_social: runs SocialPipeline and stores engagement signals."""

    def test_happy_path(self, pipeline):
        mock_social = MagicMock()
        mock_social.run.return_value = {
            "posts": [{"platform": "bluesky", "topic": "AI advances"}],
        }

        with (
            patch("orchestrator.runner.PROJECT_ROOT",
                  Path(tempfile.mkdtemp())),
            patch("social.pipeline.SocialPipeline", return_value=mock_social),
            patch("builtins.open", MagicMock(
                return_value=MagicMock(
                    __enter__=MagicMock(return_value=MagicMock(
                        read=MagicMock(return_value='{"platforms": ["bluesky"]}')
                    )),
                    __exit__=MagicMock(return_value=False)
                )
            )),
            patch("json.load", return_value={"platforms": ["bluesky"]}),
            patch("orchestrator.runner.memory.store_signal") as mock_signal,
        ):
            result = pipeline._phase_social()

        assert len(result["posts"]) == 1
        mock_signal.assert_called_once()

    def test_kill_day(self, pipeline):
        mock_social = MagicMock()
        mock_social.run.return_value = {"kill_day": True, "topic": "stale"}

        with (
            patch("orchestrator.runner.PROJECT_ROOT",
                  Path(tempfile.mkdtemp())),
            patch("social.pipeline.SocialPipeline", return_value=mock_social),
            patch("builtins.open", MagicMock(
                return_value=MagicMock(
                    __enter__=MagicMock(return_value=MagicMock(
                        read=MagicMock(return_value='{}')
                    )),
                    __exit__=MagicMock(return_value=False)
                )
            )),
            patch("json.load", return_value={}),
            patch("orchestrator.runner.memory.store_signal") as mock_signal,
        ):
            result = pipeline._phase_social()

        assert result["kill_day"] is True
        mock_signal.assert_called_once()


class TestPhaseEngagement:
    """_phase_engagement: runs EngagementPipeline."""

    def test_happy_path(self, pipeline):
        mock_eng = MagicMock()
        mock_eng.run.return_value = {"replies_posted": 3, "follows": 2}

        with (
            patch("orchestrator.runner.PROJECT_ROOT",
                  Path(tempfile.mkdtemp())),
            patch("social.engagement.EngagementPipeline", return_value=mock_eng),
            patch("builtins.open", MagicMock(
                return_value=MagicMock(
                    __enter__=MagicMock(return_value=MagicMock(
                        read=MagicMock(return_value='{}')
                    )),
                    __exit__=MagicMock(return_value=False)
                )
            )),
            patch("json.load", return_value={}),
        ):
            result = pipeline._phase_engagement()

        assert result["replies_posted"] == 3
        assert result["follows"] == 2


class TestPhaseEvolve:
    """_phase_evolve: agent trace analysis and skill improvement."""

    def test_happy_path(self, pipeline, tmp_path):
        changes = [{"file": "agents/researcher.md", "action": "update"}]
        apply_result = {"applied": 1, "reverted": 0, "skipped": 0}

        with (
            patch("orchestrator.runner.PROJECT_ROOT", tmp_path),
            patch("orchestrator.analyzer.build_analyzer_prompt",
                  return_value="analyze prompt"),
            patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                  return_value=(json.dumps(changes), 0)),
            patch("orchestrator.analyzer.parse_analyzer_output",
                  return_value=changes),
            patch("orchestrator.analyzer.apply_analyzer_changes",
                  return_value=apply_result),
        ):
            # Create trace dir structure
            trace_dir = tmp_path / "data" / "testuser" / "mindpattern" / "agents"
            trace_dir.mkdir(parents=True, exist_ok=True)

            result = pipeline._phase_evolve()

        assert result["evolved"] is True
        assert result["applied"] == 1

    def test_llm_failure_returns_not_evolved(self, pipeline, tmp_path):
        with (
            patch("orchestrator.runner.PROJECT_ROOT", tmp_path),
            patch("orchestrator.analyzer.build_analyzer_prompt",
                  return_value="prompt"),
            patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                  return_value=("", 1)),
        ):
            result = pipeline._phase_evolve()

        assert result["evolved"] is False
        assert "LLM call failed" in result["reason"]

    def test_json_parse_failure(self, pipeline, tmp_path):
        with (
            patch("orchestrator.runner.PROJECT_ROOT", tmp_path),
            patch("orchestrator.analyzer.build_analyzer_prompt",
                  return_value="prompt"),
            patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                  return_value=("not json", 0)),
            patch("orchestrator.analyzer.parse_analyzer_output",
                  return_value=None),
        ):
            result = pipeline._phase_evolve()

        assert result["evolved"] is False
        assert "JSON parse failed" in result["reason"]


class TestPhaseIdentity:
    """_phase_identity: identity maintenance via LLM."""

    def test_happy_path(self, pipeline, tmp_path):
        diff = {"changes": [{"file": "soul.md", "action": "update"}]}
        apply_result = {"changes_made": 1, "errors": []}
        pipeline.evolve_result = {"applied": 2, "reverted": 0, "skipped": 1}

        with (
            patch("orchestrator.runner.PROJECT_ROOT", tmp_path),
            patch("memory.identity_evolve.build_evolve_prompt",
                  return_value="evolve prompt"),
            patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                  return_value=(json.dumps(diff), 0)),
            patch("memory.identity_evolve.parse_llm_output",
                  return_value=diff),
            patch("memory.identity_evolve.apply_evolution_diff",
                  return_value=apply_result),
        ):
            result = pipeline._phase_identity()

        assert result["evolved"] is True
        assert result["changes_made"] == 1

    def test_llm_failure(self, pipeline, tmp_path):
        pipeline.evolve_result = {}

        with (
            patch("orchestrator.runner.PROJECT_ROOT", tmp_path),
            patch("memory.identity_evolve.build_evolve_prompt",
                  return_value="prompt"),
            patch("orchestrator.runner.agent_dispatch.run_claude_prompt",
                  return_value=("", 1)),
        ):
            result = pipeline._phase_identity()

        assert result["evolved"] is False
        assert "LLM call failed" in result["reason"]


class TestPhaseMirror:
    """_phase_mirror: generates Obsidian mirror files."""

    def test_happy_path(self, pipeline, tmp_path):
        with (
            patch("orchestrator.runner.PROJECT_ROOT", tmp_path),
            patch("memory.mirror.generate_mirrors") as mock_gen,
        ):
            result = pipeline._phase_mirror()

        assert result["mirrored"] is True
        mock_gen.assert_called_once()


class TestPhaseSync:
    """_phase_sync: syncs data to Fly.io."""

    def test_happy_path(self, pipeline, tmp_path):
        with (
            patch("orchestrator.runner.PROJECT_ROOT", tmp_path),
            patch("orchestrator.sync.sync_to_fly",
                  return_value={"success": True, "bytes_uploaded": 1024}),
        ):
            result = pipeline._phase_sync()

        assert result["success"] is True
        assert result["bytes_uploaded"] == 1024

    def test_sync_failure_returns_error(self, pipeline, tmp_path):
        with (
            patch("orchestrator.runner.PROJECT_ROOT", tmp_path),
            patch("orchestrator.sync.sync_to_fly",
                  return_value={"success": False, "error": "Connection refused"}),
        ):
            result = pipeline._phase_sync()

        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════════════
# 3. Pipeline.run() — full pipeline execution
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineRun:
    """Verify run() executes all phases in order."""

    def test_full_pipeline_all_phases_succeed(self, pipeline):
        """All phases succeed -> run() returns 0."""
        # Mock every phase handler to return a simple dict
        phase_results = {
            Phase.INIT: {"preferences_count": 5},
            Phase.TREND_SCAN: {"trends": []},
            Phase.RESEARCH: {"findings_stored": 10},
            Phase.SYNTHESIS: {"word_count": 4000},
            Phase.DELIVER: {"success": True},
            Phase.LEARN: {"quality": {"overall_score": 0.85}},
            Phase.SOCIAL: {"posts": []},
            Phase.ENGAGEMENT: {"replies_posted": 0},
            Phase.EVOLVE: {"evolved": False},
            Phase.IDENTITY: {"evolved": False},
            Phase.MIRROR: {"mirrored": True},
            Phase.SYNC: {"success": True},
        }

        def mock_handler(phase):
            if phase in phase_results:
                return lambda: phase_results[phase]
            return None

        with patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler):
            with patch.object(pipeline.checkpoint, "find_resumable_run", return_value=None):
                exit_code = pipeline.run()

        assert exit_code == 0
        assert pipeline.pipeline.current_phase == Phase.COMPLETED

    def test_run_returns_1_on_critical_failure(self, pipeline):
        """RESEARCH fails -> run() returns 1."""
        call_count = {"n": 0}

        def mock_handler(phase):
            def _init():
                return {"preferences_count": 0}

            def _trend_scan():
                return {"trends": []}

            def _research():
                raise RuntimeError("Zero findings stored")

            handlers = {
                Phase.INIT: _init,
                Phase.TREND_SCAN: _trend_scan,
                Phase.RESEARCH: _research,
            }
            return handlers.get(phase)

        with (
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
            patch.object(pipeline.checkpoint, "find_resumable_run", return_value=None),
            patch.object(pipeline, "_send_alert") as mock_alert,
        ):
            exit_code = pipeline.run()

        assert exit_code == 1
        mock_alert.assert_called_once()

    def test_pipeline_completes_with_warnings(self, pipeline):
        """A non-critical phase failure adds a warning but pipeline succeeds."""
        def mock_handler(phase):
            def _succeed():
                return {}

            def _fail_sync():
                raise RuntimeError("Connection refused")

            if phase == Phase.SYNC:
                return _fail_sync
            return _succeed

        with (
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
            patch.object(pipeline.checkpoint, "find_resumable_run", return_value=None),
        ):
            exit_code = pipeline.run()

        assert exit_code == 0
        assert len(pipeline.pipeline.warnings) >= 1


# ═══════════════════════════════════════════════════════════════════════
# 4. Error recovery — skippable vs critical
# ═══════════════════════════════════════════════════════════════════════


class TestErrorRecovery:
    """Verify that skippable phases don't stop pipeline, critical ones do."""

    def test_skippable_phase_does_not_stop_pipeline(self, pipeline):
        """Phase.INIT is skippable — failure should not stop the pipeline."""
        phases_executed = []

        def mock_handler(phase):
            def _handler():
                phases_executed.append(phase)
                if phase == Phase.INIT:
                    raise RuntimeError("Init error")
                return {}
            return _handler

        with (
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
            patch.object(pipeline.checkpoint, "find_resumable_run", return_value=None),
        ):
            exit_code = pipeline.run()

        assert exit_code == 0
        # INIT failed but pipeline continued through remaining phases
        assert Phase.INIT in phases_executed
        assert Phase.SYNC in phases_executed

    def test_critical_phase_stops_pipeline(self, pipeline):
        """Phase.RESEARCH is critical — failure should stop the pipeline."""
        phases_executed = []

        def mock_handler(phase):
            def _handler():
                phases_executed.append(phase)
                if phase == Phase.RESEARCH:
                    raise RuntimeError("Research failed")
                return {}
            return _handler

        with (
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
            patch.object(pipeline.checkpoint, "find_resumable_run", return_value=None),
            patch.object(pipeline, "_send_alert"),
        ):
            exit_code = pipeline.run()

        assert exit_code == 1
        assert Phase.RESEARCH in phases_executed
        # Phases after RESEARCH should NOT have been executed
        assert Phase.SYNTHESIS not in phases_executed
        assert Phase.DELIVER not in phases_executed

    def test_synthesis_is_critical(self, pipeline):
        """Phase.SYNTHESIS is critical — verify it stops pipeline on failure."""
        phases_executed = []

        def mock_handler(phase):
            def _handler():
                phases_executed.append(phase)
                if phase == Phase.SYNTHESIS:
                    raise RuntimeError("Synthesis failed")
                return {}
            return _handler

        with (
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
            patch.object(pipeline.checkpoint, "find_resumable_run", return_value=None),
            patch.object(pipeline, "_send_alert"),
        ):
            exit_code = pipeline.run()

        assert exit_code == 1
        assert Phase.DELIVER not in phases_executed

    def test_multiple_skippable_failures(self, pipeline):
        """Multiple non-critical phases fail — pipeline still completes."""
        def mock_handler(phase):
            def _handler():
                if phase in {Phase.INIT, Phase.SOCIAL, Phase.SYNC}:
                    raise RuntimeError(f"{phase.value} failed")
                return {}
            return _handler

        with (
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
            patch.object(pipeline.checkpoint, "find_resumable_run", return_value=None),
        ):
            exit_code = pipeline.run()

        assert exit_code == 0
        assert len(pipeline.pipeline.warnings) == 3

    def test_send_alert_called_on_critical_failure(self, pipeline):
        """Verify _send_alert is called when a critical phase fails."""
        def mock_handler(phase):
            def _handler():
                if phase == Phase.RESEARCH:
                    raise RuntimeError("Catastrophic failure")
                return {}
            return _handler

        with (
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
            patch.object(pipeline.checkpoint, "find_resumable_run", return_value=None),
            patch.object(pipeline, "_send_alert") as mock_alert,
        ):
            pipeline.run()

        mock_alert.assert_called_once()
        assert "CRITICAL" in mock_alert.call_args[0][0]
        assert "Catastrophic failure" in mock_alert.call_args[0][0]


# ═══════════════════════════════════════════════════════════════════════
# 5. Resume from checkpoint
# ═══════════════════════════════════════════════════════════════════════


class TestResumeFromCheckpoint:
    """Verify pipeline can resume from a saved checkpoint."""

    def test_resume_skips_completed_phases(self, pipeline):
        """When resuming from RESEARCH, INIT and TREND_SCAN should be skipped."""
        # Seed checkpoints: INIT and TREND_SCAN already completed
        pipeline.checkpoint.save("test-run-001", Phase.INIT, {"preferences_count": 5})
        pipeline.checkpoint.save("test-run-001", Phase.TREND_SCAN, {"trends": []})

        phases_executed = []

        def mock_handler(phase):
            def _handler():
                phases_executed.append(phase)
                return {}
            return _handler

        with (
            patch.object(pipeline.checkpoint, "find_resumable_run",
                         return_value="test-run-001"),
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
        ):
            exit_code = pipeline.run()

        assert exit_code == 0
        # INIT and TREND_SCAN should NOT be in phases_executed
        assert Phase.INIT not in phases_executed
        assert Phase.TREND_SCAN not in phases_executed
        # RESEARCH and later phases should be executed
        assert Phase.RESEARCH in phases_executed
        assert Phase.SYNC in phases_executed

    def test_resume_from_mid_pipeline(self, pipeline):
        """Resume from DELIVER (phases 1-4 already done)."""
        for phase in [Phase.INIT, Phase.TREND_SCAN, Phase.RESEARCH, Phase.SYNTHESIS]:
            pipeline.checkpoint.save("test-run-001", phase)

        phases_executed = []

        def mock_handler(phase):
            def _handler():
                phases_executed.append(phase)
                return {}
            return _handler

        with (
            patch.object(pipeline.checkpoint, "find_resumable_run",
                         return_value="test-run-001"),
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
        ):
            exit_code = pipeline.run()

        assert exit_code == 0
        # Only DELIVER onward should have run
        assert Phase.INIT not in phases_executed
        assert Phase.RESEARCH not in phases_executed
        assert Phase.DELIVER in phases_executed
        assert Phase.LEARN in phases_executed

    def test_no_resume_when_no_prior_run(self, pipeline):
        """No prior run -> starts from INIT."""
        phases_executed = []

        def mock_handler(phase):
            def _handler():
                phases_executed.append(phase)
                return {}
            return _handler

        with (
            patch.object(pipeline.checkpoint, "find_resumable_run",
                         return_value=None),
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
        ):
            exit_code = pipeline.run()

        assert exit_code == 0
        assert Phase.INIT in phases_executed

    def test_checkpoint_saved_after_each_phase(self, pipeline):
        """Verify checkpoints are written as phases complete."""
        def mock_handler(phase):
            def _handler():
                return {"phase": phase.value}
            return _handler

        with (
            patch.object(pipeline.checkpoint, "find_resumable_run",
                         return_value=None),
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
        ):
            pipeline.run()

        # Check that checkpoints were saved for all phases including COMPLETED
        completed_phases = pipeline.checkpoint.get_completed_phases("test-run-001")
        phase_values = {p.value for p in completed_phases}
        assert "init" in phase_values
        assert "research" in phase_values
        assert "sync" in phase_values
        assert "completed" in phase_values

    def test_resume_sets_correct_run_id(self, pipeline):
        """When resuming, the pipeline run_id is set to the resumed run's id."""
        pipeline.checkpoint.save("test-run-001", Phase.INIT)

        def mock_handler(phase):
            return lambda: {}

        with (
            patch.object(pipeline.checkpoint, "find_resumable_run",
                         return_value="test-run-001"),
            patch.object(pipeline, "_get_phase_handler", side_effect=mock_handler),
        ):
            pipeline.run()

        assert pipeline.pipeline.run_id == "test-run-001"


# ═══════════════════════════════════════════════════════════════════════
# 6. Helpers
# ═══════════════════════════════════════════════════════════════════════


class TestHelpers:
    """Test helper methods: _keychain_lookup, _send_alert, close."""

    def test_keychain_lookup_returns_none_on_failure(self, pipeline):
        import subprocess as sp
        with patch("subprocess.check_output",
                    side_effect=sp.CalledProcessError(44, "security")):
            result = pipeline._keychain_lookup("nonexistent")
        assert result is None

    def test_send_alert_no_phone(self, pipeline):
        """If no phone is configured, alert just logs."""
        pipeline.user_config["phone"] = None
        # Should not raise
        pipeline._send_alert("test message")

    def test_send_alert_with_phone(self, pipeline):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            pipeline._send_alert("test alert")
        mock_run.assert_called_once()

    def test_close(self, pipeline):
        mock_db = MagicMock()
        mock_traces = MagicMock()
        pipeline.db = mock_db
        pipeline.traces_conn = mock_traces

        pipeline.close()

        mock_db.close.assert_called_once()
        mock_traces.close.assert_called_once()
