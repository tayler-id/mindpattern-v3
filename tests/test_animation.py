"""Tests for the animation pipeline.

All external API calls, Claude CLI calls, and Node.js/Remotion calls are mocked.
No real HTTP requests, renders, or LLM calls are made.
"""

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch, PropertyMock

import pytest

import importlib
import importlib.util

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# gif-gen.py uses a hyphen (matching image-gen.py convention), so import via spec
_spec = importlib.util.spec_from_file_location(
    "gif_gen", PROJECT_ROOT / "tools" / "gif-gen.py"
)
gif_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gif_gen)

# We test social.animation after importing, but need to mock dependencies


# ────────────────────────────────────────────────────────────────────────
# FIXTURES
# ────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """In-memory SQLite DB with minimal schema for animation tests."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE social_posts (
            id INTEGER PRIMARY KEY,
            date TEXT,
            platform TEXT,
            content TEXT,
            posted INTEGER DEFAULT 0,
            brief_json TEXT
        )"""
    )
    db.commit()
    return db


@pytest.fixture
def sample_brief():
    return {
        "editorial_angle": "AI agents are replacing entire SaaS workflows",
        "topic": "AI agents displacing SaaS",
        "anchor": "AI agents displacing SaaS",
    }


@pytest.fixture
def sample_concept():
    return {
        "concept": "Bar chart showing AI adoption rate accelerating",
        "style": "data_visualization",
        "motion_design": "Bars grow sequentially with spring physics",
        "color_palette": ["#1a1a2e", "#16213e", "#0f3460", "#e94560"],
        "typography": {"headline": "Inter Bold", "body": "Inter Regular"},
        "duration_seconds": 4,
        "loop_strategy": "seamless_fade",
        "headline": "AI Adoption Rate",
        "data_points": {"values": [10, 25, 45, 70, 95], "labels": ["2022", "2023", "2024", "2025", "2026"]},
    }


# ────────────────────────────────────────────────────────────────────────
# COMPOSITION VALIDATOR TESTS
# ────────────────────────────────────────────────────────────────────────


class TestCompositionValidator:
    """Tests for gif_gen._validate_composition()."""

    def test_valid_composition(self, tmp_path):
        comp = tmp_path / "valid.tsx"
        comp.write_text(
            'import React from "react";\n'
            'import { AbsoluteFill } from "remotion";\n'
            'import { Signature } from "./Signature";\n'
            "export const Test = () => <AbsoluteFill />;\n"
        )
        errors = gif_gen._validate_composition(comp)
        assert errors == []

    def test_blocks_fs_import(self, tmp_path):
        comp = tmp_path / "bad_fs.tsx"
        comp.write_text('import fs from "fs";\nexport const Test = () => null;\n')
        errors = gif_gen._validate_composition(comp)
        assert any("fs" in e for e in errors)

    def test_blocks_child_process(self, tmp_path):
        comp = tmp_path / "bad_cp.tsx"
        comp.write_text('import { exec } from "child_process";\nexport const Test = () => null;\n')
        errors = gif_gen._validate_composition(comp)
        assert any("child_process" in e for e in errors)

    def test_blocks_http(self, tmp_path):
        comp = tmp_path / "bad_http.tsx"
        comp.write_text('import http from "http";\nexport const Test = () => null;\n')
        errors = gif_gen._validate_composition(comp)
        assert any("http" in e for e in errors)

    def test_blocks_require(self, tmp_path):
        comp = tmp_path / "bad_require.tsx"
        comp.write_text('const os = require("os");\nexport const Test = () => null;\n')
        errors = gif_gen._validate_composition(comp)
        assert any("os" in e for e in errors)

    def test_allows_remotion_imports(self, tmp_path):
        comp = tmp_path / "remotion_imports.tsx"
        comp.write_text(
            'import { useCurrentFrame, spring } from "remotion";\n'
            'import { Gif } from "@remotion/gif";\n'
            "export const Test = () => null;\n"
        )
        errors = gif_gen._validate_composition(comp)
        assert errors == []

    def test_blocks_unknown_package(self, tmp_path):
        comp = tmp_path / "unknown.tsx"
        comp.write_text(
            'import axios from "axios";\nexport const Test = () => null;\n'
        )
        errors = gif_gen._validate_composition(comp)
        assert any("axios" in e for e in errors)

    def test_file_not_found(self, tmp_path):
        comp = tmp_path / "nonexistent.tsx"
        errors = gif_gen._validate_composition(comp)
        assert any("not found" in e.lower() for e in errors)


# ────────────────────────────────────────────────────────────────────────
# GIF OPTIMIZATION TESTS
# ────────────────────────────────────────────────────────────────────────


class TestGifOptimization:
    """Tests for gif_gen._optimize_gif()."""

    def test_under_limit_no_optimization(self, tmp_path):
        gif = tmp_path / "small.gif"
        gif.write_bytes(b"GIF89a" + b"\x00" * 500)  # ~500 bytes
        with patch.object(gif_gen, "_find_gifsicle", return_value="/usr/local/bin/gifsicle"):
            result = gif_gen._optimize_gif(gif, 1_000_000)
        assert result is True

    def test_gifsicle_not_found(self, tmp_path):
        gif = tmp_path / "big.gif"
        gif.write_bytes(b"GIF89a" + b"\x00" * 2_000_000)
        with patch.object(gif_gen, "_find_gifsicle", return_value=None):
            result = gif_gen._optimize_gif(gif, 1_000_000)
        assert result is False


# ────────────────────────────────────────────────────────────────────────
# ANIMATION PIPELINE TESTS
# ────────────────────────────────────────────────────────────────────────


class TestAnimationPipeline:
    """Tests for social.animation module."""

    def test_get_recent_styles_empty_db(self, mock_db):
        from social.animation import _get_recent_animation_styles
        styles = _get_recent_animation_styles(mock_db)
        assert styles == []

    def test_get_recent_styles_with_data(self, mock_db):
        from social.animation import _get_recent_animation_styles
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        mock_db.execute(
            "INSERT INTO social_posts (date, platform, content, brief_json) VALUES (?, ?, ?, ?)",
            (today, "bluesky", "test", json.dumps({"animation_style": "spotlight"})),
        )
        mock_db.commit()

        styles = _get_recent_animation_styles(mock_db)
        assert "spotlight" in styles

    def test_build_props_kinetic_typography(self, sample_concept):
        from social.animation import _build_props_for_style

        sample_concept["style"] = "kinetic_typography"
        sample_concept["headline"] = "AI is eating the world"
        props = _build_props_for_style("kinetic_typography", sample_concept, {})

        assert props["headline"] == "AI is eating the world"
        assert "accent" in props
        assert "backgroundColor" in props

    def test_build_props_data_viz(self, sample_concept):
        from social.animation import _build_props_for_style

        props = _build_props_for_style("data_visualization", sample_concept, {})
        assert "values" in props
        assert "labels" in props
        assert props["title"] == "AI Adoption Rate"

    def test_build_props_spotlight(self, sample_concept):
        from social.animation import _build_props_for_style

        sample_concept["stat"] = "10x"
        sample_concept["label"] = "faster with AI"
        props = _build_props_for_style("spotlight", sample_concept, {})
        assert props["stat"] == "10x"

    def test_build_props_concept_animation(self, sample_concept):
        from social.animation import _build_props_for_style

        sample_concept["concept_type"] = "network"
        props = _build_props_for_style("concept_animation", sample_concept, {})
        assert props["concept"] == "network"

    def test_build_props_concept_animation_invalid_type(self, sample_concept):
        from social.animation import _build_props_for_style

        sample_concept["concept_type"] = "invalid_type"
        props = _build_props_for_style("concept_animation", sample_concept, {})
        assert props["concept"] == "network"  # defaults to network

    @patch("social.animation.create_art")
    def test_fallback_on_remotion_not_installed(self, mock_create_art, mock_db, sample_brief):
        from social.animation import create_animation

        mock_create_art.return_value = {"approved": False, "skipped": True}

        with patch("social.animation.REMOTION_DIR", Path("/nonexistent")):
            result = create_animation(db=mock_db, brief=sample_brief, date_str="2026-04-03")

        mock_create_art.assert_called_once()

    @patch("social.animation.create_art")
    @patch("social.animation._animation_director_conceive")
    def test_fallback_on_director_failure(self, mock_director, mock_create_art, mock_db, sample_brief):
        from social.animation import create_animation, REMOTION_DIR

        mock_director.return_value = None
        mock_create_art.return_value = {"approved": False}

        # Mock REMOTION_DIR existence
        with patch("social.animation.REMOTION_DIR", PROJECT_ROOT):
            with patch.object(Path, "exists", return_value=True):
                result = create_animation(db=mock_db, brief=sample_brief, date_str="2026-04-03")

        mock_create_art.assert_called_once()


# ────────────────────────────────────────────────────────────────────────
# PARSE JSON RESPONSE TESTS
# ────────────────────────────────────────────────────────────────────────


class TestParseJsonResponse:
    """Tests for _parse_json_response shared by art.py and animation.py."""

    def test_direct_parse(self):
        from social.animation import _parse_json_response
        raw = '{"concept": "test", "style": "spotlight"}'
        result = _parse_json_response(raw, "concept")
        assert result["concept"] == "test"

    def test_embedded_json(self):
        from social.animation import _parse_json_response
        raw = 'Here is the result:\n{"concept": "test", "style": "spotlight"}\nDone.'
        result = _parse_json_response(raw, "concept")
        assert result is not None
        assert result["concept"] == "test"

    def test_missing_key(self):
        from social.animation import _parse_json_response
        raw = '{"other": "value"}'
        result = _parse_json_response(raw, "concept")
        assert result is None

    def test_invalid_json(self):
        from social.animation import _parse_json_response
        raw = "this is not json at all"
        result = _parse_json_response(raw, "concept")
        assert result is None


# ────────────────────────────────────────────────────────────────────────
# CLEANUP TESTS
# ────────────────────────────────────────────────────────────────────────


class TestCleanup:
    """Tests for composition cleanup."""

    def test_cleanup_old_compositions(self, tmp_path):
        from social.animation import _cleanup_old_compositions

        # Create an old file
        old_file = tmp_path / "old.tsx"
        old_file.write_text("old")
        old_mtime = os.path.getmtime(old_file) - 8 * 86400
        os.utime(old_file, (old_mtime, old_mtime))

        # Create a new file
        new_file = tmp_path / "new.tsx"
        new_file.write_text("new")

        with patch("social.animation.COMPOSITIONS_DIR", tmp_path):
            _cleanup_old_compositions(days=7)

        assert not old_file.exists()
        assert new_file.exists()
