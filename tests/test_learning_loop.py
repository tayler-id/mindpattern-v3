"""Tests for the agent-notes learning loop.

The loop was wired end to end but starved: nothing in the daily pipeline
wrote agent_notes, so consolidate() clustered an empty table every run and
validated_patterns froze on 2026-04-09. These tests pin the two defects.
"""

import sqlite3

import numpy as np
import pytest

from memory.db import _init_schema


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_schema(conn)
    yield conn
    conn.close()


# ── Defect 1: agents never emit notes ────────────────────────────────────


class TestAgentNoteParsing:
    def test_parses_notes_array_from_agent_output(self):
        from orchestrator.agents import _parse_notes

        output = """{
          "findings": [],
          "notes": [
            {"note_type": "source_quality",
             "content": "arXiv cs.AI gave 6 builder-actionable papers today."},
            {"note_type": "search_strategy",
             "content": "Exa beat WebSearch for agent-framework releases."}
          ]
        }"""
        notes = _parse_notes(output, "arxiv-researcher")
        assert len(notes) == 2
        assert notes[0]["note_type"] == "source_quality"
        assert "arXiv" in notes[0]["content"]

    def test_missing_notes_key_returns_empty_list(self):
        from orchestrator.agents import _parse_notes

        assert _parse_notes('{"findings": []}', "a") == []

    def test_unparseable_output_returns_empty_list(self):
        from orchestrator.agents import _parse_notes

        assert _parse_notes("I cannot help with that.", "a") == []

    def test_drops_note_entries_missing_required_fields(self):
        from orchestrator.agents import _parse_notes

        output = """{"findings": [], "notes": [
            {"note_type": "source_quality", "content": "good"},
            {"note_type": "source_quality"},
            {"content": "no type"},
            "not an object",
            {"note_type": "x", "content": ""}
        ]}"""
        notes = _parse_notes(output, "a")
        assert len(notes) == 1
        assert notes[0]["content"] == "good"

    def test_note_content_is_truncated_to_a_sane_length(self):
        from orchestrator.agents import _parse_notes, MAX_NOTE_CHARS

        output = (
            '{"findings": [], "notes": [{"note_type": "pattern", "content": "'
            + "x" * (MAX_NOTE_CHARS + 500)
            + '"}]}'
        )
        notes = _parse_notes(output, "a")
        assert len(notes[0]["content"]) == MAX_NOTE_CHARS

    def test_note_count_is_capped_per_agent(self):
        from orchestrator.agents import _parse_notes, MAX_NOTES_PER_AGENT

        items = ", ".join(
            f'{{"note_type": "pattern", "content": "note {i}"}}'
            for i in range(MAX_NOTES_PER_AGENT + 10)
        )
        notes = _parse_notes('{"findings": [], "notes": [' + items + "]}", "a")
        assert len(notes) == MAX_NOTES_PER_AGENT


class TestAgentResultCarriesNotes:
    def test_agent_result_has_notes_field_defaulting_empty(self):
        from orchestrator.agents import AgentResult

        assert AgentResult(agent_name="a").notes == []


class TestPromptRequestsNotes:
    def test_agent_prompt_asks_for_the_notes_array(self, tmp_path):
        from orchestrator.agents import build_agent_prompt

        soul = tmp_path / "SOUL.md"
        soul.write_text("soul")
        skill = tmp_path / "skill.md"
        skill.write_text("skill")

        prompt = build_agent_prompt(
            agent_name="arxiv-researcher",
            user_id="ramsay",
            date_str="2026-08-21",
            soul_path=soul,
            agent_skill_path=skill,
            context="",
        )
        assert '"notes"' in prompt
        assert "note_type" in prompt
        assert "source_quality" in prompt


# ── Defect 2: consolidate() cannot see promoted patterns ─────────────────


class TestConsolidateSeesPromotedPatterns:
    def _add_note(self, db, agent, content, note_type="source_quality"):
        from memory.patterns import store_note

        return store_note(db, "2026-08-21", agent, note_type, content)

    def test_matching_note_updates_promoted_pattern_instead_of_duplicating(
        self, db, monkeypatch
    ):
        """A promoted pattern must still absorb new observations.

        promote() flips a matured pattern to status='promoted'. consolidate()
        only loaded status='active', so from then on every matching note
        created a *duplicate* pattern instead of incrementing the original.
        """
        import memory.patterns as patterns
        from memory.embeddings import serialize_f32

        vec = np.zeros(384, dtype=np.float32)
        vec[0] = 1.0
        monkeypatch.setattr(patterns, "embed_text", lambda _t: vec.tolist())

        db.execute(
            """INSERT INTO validated_patterns
               (pattern_key, distilled_rule, source_agents, observation_count,
                first_seen, last_seen, status, created_at)
               VALUES ('sourcequality-arxiv', 'arXiv is high quality',
                       'arxiv-researcher', 5, '2026-04-01', '2026-04-09',
                       'promoted', '2026-04-09T00:00:00')"""
        )
        pid = db.execute(
            "SELECT id FROM validated_patterns"
        ).fetchone()["id"]
        db.execute(
            "INSERT INTO validated_patterns_embeddings (pattern_id, embedding)"
            " VALUES (?, ?)",
            (pid, serialize_f32(vec.tolist())),
        )
        db.commit()

        for agent in ("arxiv-researcher", "sources-researcher", "hn-researcher"):
            self._add_note(db, agent, "arXiv is high quality")

        result = patterns.consolidate(db)

        total = db.execute(
            "SELECT COUNT(*) c FROM validated_patterns"
        ).fetchone()["c"]
        assert total == 1, "consolidate created a duplicate of a promoted pattern"
        assert result["updated"] == 1
        row = db.execute(
            "SELECT observation_count FROM validated_patterns WHERE id = ?",
            (pid,),
        ).fetchone()
        assert row["observation_count"] > 5


class TestOrphanEmbeddingCleanup:
    def test_prune_removes_pattern_embeddings_with_no_pattern(self, db):
        from memory.embeddings import serialize_f32
        from memory.patterns import prune

        vec = [0.0] * 384
        # The production DB accumulated 35 of these before foreign_keys was
        # enforced, so recreate that state rather than the enforced one.
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute(
            "INSERT INTO validated_patterns_embeddings (pattern_id, embedding)"
            " VALUES (9999, ?)",
            (serialize_f32(vec),),
        )
        db.commit()
        db.execute("PRAGMA foreign_keys=ON")

        result = prune(db)

        left = db.execute(
            "SELECT COUNT(*) c FROM validated_patterns_embeddings"
        ).fetchone()["c"]
        assert left == 0
        assert result["orphan_embeddings_removed"] == 1


# ── Wiring: the research phase must actually persist what agents emit ────


class TestResearchPhaseStoresNotes:
    def test_stores_every_note_from_every_agent(self, db, monkeypatch):
        import memory.patterns as patterns
        from orchestrator.agents import AgentResult
        from orchestrator.runner import _store_agent_notes

        monkeypatch.setattr(
            patterns, "embed_text", lambda _t: [0.0] * 384
        )

        results = [
            AgentResult(
                agent_name="arxiv-researcher",
                notes=[
                    {"note_type": "source_quality", "content": "cs.AI paid off"},
                    {"note_type": "skip_list", "content": "cs.NE is noise"},
                ],
            ),
            AgentResult(
                agent_name="hn-researcher",
                notes=[{"note_type": "pattern", "content": "Show HN peaks Tue"}],
            ),
            AgentResult(agent_name="rss-researcher"),
        ]

        stored = _store_agent_notes(db, results, "2026-08-21")

        assert stored == 3
        rows = db.execute(
            "SELECT agent, note_type, content FROM agent_notes ORDER BY id"
        ).fetchall()
        assert [r["agent"] for r in rows] == [
            "arxiv-researcher", "arxiv-researcher", "hn-researcher",
        ]
        assert rows[1]["note_type"] == "skip_list"

    def test_one_bad_note_does_not_lose_the_others(self, db, monkeypatch):
        import memory.patterns as patterns
        from orchestrator.agents import AgentResult
        from orchestrator.runner import _store_agent_notes

        calls = {"n": 0}

        def flaky_embed(_text):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("embedding model unavailable")
            return [0.0] * 384

        monkeypatch.setattr(patterns, "embed_text", flaky_embed)

        results = [
            AgentResult(
                agent_name="a",
                notes=[
                    {"note_type": "pattern", "content": "first blows up"},
                    {"note_type": "pattern", "content": "second must survive"},
                ],
            )
        ]

        stored = _store_agent_notes(db, results, "2026-08-21")

        assert stored == 1
        row = db.execute("SELECT content FROM agent_notes").fetchone()
        assert row["content"] == "second must survive"
