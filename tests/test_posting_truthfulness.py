"""M0 Task 10 — posting truthfulness (audit C5).

Failed platform posts must be recorded as failures, receipts must be claimed
before every post (crash/concurrency dedup), the kill switch must block
posting, and the expeditor verdict file must be per-run.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import memory
from core import migrations, receipts


def fake_embed_text(text):
    """Deterministic fake embedding (no model load)."""
    np.random.seed(hash(text) % 2**32)
    vec = np.random.randn(384).astype(np.float32)
    return (vec / np.linalg.norm(vec)).tolist()


@pytest.fixture
def db(tmp_path):
    conn = memory.get_db(tmp_path / "memory.db", user_id="test")
    migrations.migrate(conn)
    yield conn
    conn.close()


def make_pipeline(db):
    """SocialPipeline with no real clients, policy mocked permissive."""
    config = {"platforms": {}, "gate_timeout_seconds": 5}
    with patch("social.pipeline.PolicyEngine") as MockPE, \
         patch("social.pipeline.ApprovalGateway"):
        mock_policy = MagicMock()
        mock_policy.validate_post_rate_limit.return_value = None
        mock_policy.validate_rate_limits.return_value = {
            "allowed": True, "reason": "", "current": 0, "limit": 10,
        }
        MockPE.load_social.return_value = mock_policy

        from social.pipeline import SocialPipeline

        return SocialPipeline(user_id="test", config=config, db=db)


def failing_client(error="HTTP 400: bad request"):
    client = MagicMock()
    client.post.return_value = {"success": False, "url": "", "id": "", "error": error}
    return client


def succeeding_client():
    client = MagicMock()
    client.post.return_value = {
        "success": True, "url": "https://example.com/1", "id": "1",
    }
    return client


class TestPostWithJitterTruthfulness:
    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_failed_post_recorded_as_failure(self, _embed, db):
        pipeline = make_pipeline(db)
        pipeline._platform_clients = {"bluesky": failing_client()}

        results = pipeline._post_with_jitter({"bluesky": "hello world"}, {})

        assert results[0]["error"] == "HTTP 400: bad request"
        row = db.execute(
            "SELECT posted FROM social_posts WHERE platform='bluesky'"
        ).fetchone()
        assert row["posted"] == 0
        eng = db.execute(
            "SELECT status FROM engagements WHERE platform='bluesky'"
        ).fetchone()
        assert eng["status"] == "failed"

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_client_exception_recorded_as_failure(self, _embed, db):
        pipeline = make_pipeline(db)
        client = MagicMock()
        client.post.side_effect = RuntimeError("connection reset")
        pipeline._platform_clients = {"bluesky": client}

        results = pipeline._post_with_jitter({"bluesky": "hello"}, {})

        assert "connection reset" in results[0]["error"]
        row = db.execute("SELECT posted FROM social_posts").fetchone()
        assert row["posted"] == 0

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_successful_post_recorded_as_posted(self, _embed, db):
        pipeline = make_pipeline(db)
        pipeline._platform_clients = {"bluesky": succeeding_client()}

        results = pipeline._post_with_jitter({"bluesky": "hello"}, {})

        assert results[0]["error"] is None
        assert results[0]["url"] == "https://example.com/1"
        row = db.execute("SELECT posted FROM social_posts").fetchone()
        assert row["posted"] == 1

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_receipt_blocks_duplicate_post(self, _embed, db):
        """Concurrent pipeline / crash-resume: second post of same content skips."""
        pipeline = make_pipeline(db)
        client = succeeding_client()
        pipeline._platform_clients = {"bluesky": client}

        key = f"post:bluesky:{pipeline.date_str}:{receipts.content_key('hello')}"
        assert receipts.claim(db, key)  # another pipeline got there first

        results = pipeline._post_with_jitter({"bluesky": "hello"}, {})

        client.post.assert_not_called()
        assert "receipt" in results[0]["error"]

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_receipt_released_on_failure_so_retry_can_claim(self, _embed, db):
        pipeline = make_pipeline(db)
        pipeline._platform_clients = {"bluesky": failing_client()}

        pipeline._post_with_jitter({"bluesky": "hello"}, {})

        key = f"post:bluesky:{pipeline.date_str}:{receipts.content_key('hello')}"
        assert receipts.claim(db, key)  # receipt was freed after the failure

    def test_kill_switch_blocks_posting(self, db, monkeypatch):
        monkeypatch.setenv("MP_DISABLE_OUTBOUND", "1")
        pipeline = make_pipeline(db)
        client = succeeding_client()
        pipeline._platform_clients = {"bluesky": client}

        results = pipeline._post_with_jitter({"bluesky": "hello"}, {})

        client.post.assert_not_called()
        assert "MP_DISABLE_OUTBOUND" in results[0]["error"]

    def test_disabled_platform_never_posts(self, db):
        """A platform disabled in config gets no client and cannot post."""
        pipeline = make_pipeline(db)  # platforms: {} — nothing enabled

        assert pipeline._platform_clients == {}
        results = pipeline._post_with_jitter({"bluesky": "hello"}, {})
        assert "No client configured" in results[0]["error"]
        assert db.execute("SELECT COUNT(*) c FROM social_posts").fetchone()["c"] == 0


class TestPostPendingTruthfulness:
    def _store_ready_pending(self, db, content="pending hello"):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        return memory.store_pending_post(
            db, platform="bluesky", content=content, post_after=past
        )

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_failed_pending_post_stays_pending(self, _embed, db):
        pipeline = make_pipeline(db)
        pipeline._platform_clients = {"bluesky": failing_client()}
        pending_id = self._store_ready_pending(db)

        with patch.object(pipeline, "_in_posting_window", return_value=True):
            results = pipeline._post_pending(["bluesky"])

        assert results[0]["error"] == "HTTP 400: bad request"
        row = db.execute(
            "SELECT posted FROM pending_posts WHERE id=?", (pending_id,)
        ).fetchone()
        assert row["posted"] == 0  # still pending — will retry next run
        failed = db.execute(
            "SELECT posted FROM social_posts WHERE platform='bluesky'"
        ).fetchone()
        assert failed["posted"] == 0

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_successful_pending_post_marked_done(self, _embed, db):
        pipeline = make_pipeline(db)
        pipeline._platform_clients = {"bluesky": succeeding_client()}
        pending_id = self._store_ready_pending(db)

        with patch.object(pipeline, "_in_posting_window", return_value=True):
            results = pipeline._post_pending(["bluesky"])

        assert results[0]["error"] is None
        row = db.execute(
            "SELECT posted FROM pending_posts WHERE id=?", (pending_id,)
        ).fetchone()
        assert row["posted"] == 1

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_already_receipted_pending_marked_done_without_reposting(
        self, _embed, db
    ):
        pipeline = make_pipeline(db)
        client = succeeding_client()
        pipeline._platform_clients = {"bluesky": client}
        pending_id = self._store_ready_pending(db, content="dup content")

        key = (
            f"post:bluesky:{pipeline.date_str}:"
            f"{receipts.content_key('dup content')}"
        )
        receipts.claim(db, key)

        with patch.object(pipeline, "_in_posting_window", return_value=True):
            pipeline._post_pending(["bluesky"])

        client.post.assert_not_called()
        row = db.execute(
            "SELECT posted FROM pending_posts WHERE id=?", (pending_id,)
        ).fetchone()
        assert row["posted"] == 1  # marked done so it doesn't retry forever


class TestExpeditorVerdictFile:
    def test_verdict_file_is_per_run(self):
        """Two expedite() calls must not share an output file path."""
        captured = []

        def capture(**kwargs):
            captured.append(kwargs["output_file"])
            return {"verdict": "PASS", "feedback": "", "platform_verdicts": {}}

        from social.critics import expedite

        with patch("social.critics.run_agent_with_files", side_effect=capture):
            expedite({"bluesky": "draft one"}, {"topic": "t"}, {})
            expedite({"bluesky": "draft two"}, {"topic": "t"}, {})

        assert len(captured) == 2
        assert captured[0] != captured[1]
        for path in captured:
            assert not path.endswith("expedite-verdict.json")  # legacy shared name

    def test_verdict_tempfile_cleaned_up(self, tmp_path):
        from pathlib import Path

        from social.critics import expedite

        seen = {}

        def capture(**kwargs):
            seen["path"] = kwargs["output_file"]
            return {"verdict": "PASS", "feedback": "", "platform_verdicts": {}}

        with patch("social.critics.run_agent_with_files", side_effect=capture):
            expedite({"bluesky": "draft"}, {}, {})

        assert not Path(seen["path"]).exists()
