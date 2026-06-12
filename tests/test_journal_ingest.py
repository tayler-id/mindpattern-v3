"""M0 Task 15 — Fly→Mac journal.

Phone posts made through the Fly bot must land in the Mac's memory.db on
the next pipeline run (dedup/caps/receipts see them), with idempotent
re-ingest and offset tracking.
"""

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import memory
from core import migrations, receipts
from orchestrator import journal_ingest


def fake_embed_text(text):
    np.random.seed(hash(text) % 2**32)
    vec = np.random.randn(384).astype(np.float32)
    return (vec / np.linalg.norm(vec)).tolist()


@pytest.fixture
def db(tmp_path):
    conn = memory.get_db(tmp_path / "memory.db", user_id="test")
    migrations.migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def offset_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_ingest, "PROJECT_ROOT", tmp_path)
    return tmp_path


def post_line(content="phone post", platform="bluesky", date="2026-06-11"):
    return json.dumps({
        "id": "abc123", "ts": f"{date} 12:00:00", "type": "post",
        "platform": platform, "content": content, "date": date,
        "url": "https://example.com/p/1",
    })


class TestIngestLines:
    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_phone_post_lands_in_memory_db(self, _embed, db):
        result = journal_ingest.ingest_lines(db, "test", [post_line()])

        assert result["ingested"] == 1
        row = db.execute(
            "SELECT platform, content, posted FROM social_posts"
        ).fetchone()
        assert row["platform"] == "bluesky"
        assert row["content"] == "phone post"
        assert row["posted"] == 1
        eng = db.execute("SELECT status FROM engagements").fetchone()
        assert eng["status"] == "posted"

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_reingest_is_idempotent(self, _embed, db):
        journal_ingest.ingest_lines(db, "test", [post_line()])
        result = journal_ingest.ingest_lines(db, "test", [post_line()])

        assert result["ingested"] == 0
        assert result["skipped"] == 1
        count = db.execute("SELECT COUNT(*) c FROM social_posts").fetchone()["c"]
        assert count == 1

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_phone_post_blocks_pipeline_same_content_post(self, _embed, db):
        """The receipt the ingest claims is the same key the pipeline claims
        before posting — a phone post prevents a duplicate pipeline post."""
        journal_ingest.ingest_lines(db, "test", [post_line(content="hello")])

        key = f"post:bluesky:2026-06-11:{receipts.content_key('hello')}"
        assert receipts.claim(db, key) is False

    def test_malformed_and_unknown_lines_counted(self, db):
        lines = ["not json", json.dumps({"type": "reaction", "emoji": "+1"})]
        result = journal_ingest.ingest_lines(db, "test", lines)
        assert result["malformed"] == 1
        assert result["skipped"] == 1


class TestPullAndIngest:
    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_offset_tracked_across_pulls(self, _embed, db, offset_dir):
        first_journal = post_line(content="post one")
        with patch.object(
            journal_ingest, "_fly_ssh",
            return_value={"success": True, "output": first_journal},
        ):
            r1 = journal_ingest.pull_and_ingest(db, "test")
        assert r1["ingested"] == 1

        # Second pull: same line plus one new — only the new line is read
        two_lines = first_journal + "\n" + post_line(content="post two")
        with patch.object(
            journal_ingest, "_fly_ssh",
            return_value={"success": True, "output": two_lines},
        ):
            r2 = journal_ingest.pull_and_ingest(db, "test")
        assert r2["new_lines"] == 1
        assert r2["ingested"] == 1

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_rotated_journal_resets_offset_without_duplicates(
        self, _embed, db, offset_dir
    ):
        line = post_line(content="survivor")
        with patch.object(
            journal_ingest, "_fly_ssh",
            return_value={"success": True, "output": line + "\n" + post_line(content="x2")},
        ):
            journal_ingest.pull_and_ingest(db, "test")

        # Journal rotated on Fly: now shorter than the stored offset
        with patch.object(
            journal_ingest, "_fly_ssh",
            return_value={"success": True, "output": line},
        ):
            r = journal_ingest.pull_and_ingest(db, "test")

        assert r["ingested"] == 0  # receipt-deduped, no double row
        count = db.execute("SELECT COUNT(*) c FROM social_posts").fetchone()["c"]
        assert count == 2

    def test_fetch_failure_reported(self, db, offset_dir):
        with patch.object(
            journal_ingest, "_fly_ssh",
            return_value={"success": False, "error": "ssh down"},
        ):
            r = journal_ingest.pull_and_ingest(db, "test")
        assert r["error"] == "ssh down"


class TestJournalWriter:
    def test_append_writes_json_line(self, tmp_path, monkeypatch):
        from slack_bot import journal

        monkeypatch.setenv("MP_JOURNAL_PATH", str(tmp_path / "j.jsonl"))
        entry = journal.append({"type": "post", "platform": "bluesky",
                                "content": "hi", "date": "2026-06-11"})

        lines = (tmp_path / "j.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["type"] == "post"
        assert parsed["id"] == entry["id"]
        assert parsed["ts"]  # stamped
