import ast
import json
from pathlib import Path


def test_build_audio_script_removes_markdown_noise_and_preserves_sources(tmp_path):
    from orchestrator.audio_briefing import build_audio_script

    report = tmp_path / "2026-06-28.md"
    report.write_text(
        """# MindPattern Research Agent - June 28, 2026

Opening paragraph with a [primary source](https://example.com/source-one) and a raw URL https://raw.example.com/noise.

| Column | Value |
|---|---|
| noisy | table |

```python
print("do not speak code")
```

## Top Stories

**Agent Reach restores social search reliability.** It connects X, Reddit,
YouTube, and Exa so research is less brittle. [Source](https://example.com/source-two)

## Skills of the Day

1. Keep source evidence visible.
""",
    )

    result = build_audio_script(report, date="2026-06-28", user="ramsay")

    assert result["status"] == "ready"
    assert result["degraded"] is False
    assert result["date"] == "2026-06-28"
    assert "AI-generated audio briefing" in result["labels"]
    assert "print(" not in result["script"]
    assert "|" not in result["script"]
    assert "https://raw.example.com/noise" not in result["script"]
    assert "https://example.com/source-one" not in result["script"]
    assert "primary source" in result["script"]
    assert result["source_count"] == 2
    assert result["show_notes"][0]["url"] == "https://example.com/source-one"
    assert result["show_notes"][1]["url"] == "https://example.com/source-two"
    assert "Source notes" in result["transcript_markdown"]
    assert "https://example.com/source-two" in result["transcript_markdown"]


def test_build_audio_script_marks_degraded_report_visibly(tmp_path):
    from orchestrator.audio_briefing import build_audio_script

    report = tmp_path / "2026-06-28.md"
    report.write_text(
        """> Degraded issue notice: quality floor degraded (source balance weak).

# MindPattern Research Agent - June 28, 2026

This report has useful context, but source coverage was degraded.
""",
    )

    result = build_audio_script(report, date="2026-06-28", user="ramsay")

    assert result["status"] == "degraded"
    assert result["degraded"] is True
    assert "Degraded audio briefing" in result["labels"]
    assert result["script"].startswith("This audio briefing is marked degraded.")
    assert "quality floor degraded" in result["degraded_reason"]


def test_build_audio_script_missing_report_fails_cleanly(tmp_path):
    from orchestrator.audio_briefing import build_audio_script

    result = build_audio_script(
        tmp_path / "missing.md",
        date="2026-06-28",
        user="ramsay",
    )

    assert result["status"] == "failed"
    assert result["script"] == ""
    assert "missing" in result["error"].lower()


def test_build_tts_audio_dry_run_is_deterministic_and_does_not_call_provider(tmp_path):
    from unittest.mock import MagicMock

    from orchestrator.audio_briefing import build_audio_script, build_tts_audio

    report = tmp_path / "2026-06-28.md"
    report.write_text(
        """# MindPattern Research Agent - June 28, 2026

Agent Reach restores source coverage. [Source](https://example.com/source)
""",
    )
    script_result = build_audio_script(report, date="2026-06-28", user="ramsay")
    provider = MagicMock()

    first = build_tts_audio(script_result, dry_run=True, tts_provider=provider)
    second = build_tts_audio(script_result, dry_run=True, tts_provider=provider)

    provider.assert_not_called()
    assert first == second
    assert first["status"] == "ready"
    assert first["mode"] == "dry_run"
    assert first["audio_bytes"] is None
    assert first["metadata"]["provider"] == "dry_run"
    assert first["metadata"]["audio_placeholder"] is True
    assert first["metadata"]["script_hash"] == script_result["script_hash"]
    assert first["metadata"]["source_report_hash"] == script_result["source_report_hash"]
    assert "AI-generated audio" in first["metadata"]["labels"]
    assert "manual publish only" in first["metadata"]["labels"]


def test_build_tts_audio_dry_run_preserves_degraded_status(tmp_path):
    from orchestrator.audio_briefing import build_audio_script, build_tts_audio

    report = tmp_path / "2026-06-28.md"
    report.write_text(
        """> Degraded issue notice: source diversity too weak.

# MindPattern Research Agent - June 28, 2026

The issue should carry its degraded label into audio.
""",
    )
    script_result = build_audio_script(report, date="2026-06-28", user="ramsay")

    result = build_tts_audio(script_result, dry_run=True)

    assert result["status"] == "degraded"
    assert result["metadata"]["degraded"] is True
    assert "Degraded audio briefing" in result["metadata"]["labels"]
    assert result["metadata"]["audio_placeholder"] is True


def test_build_tts_audio_fails_closed_when_live_config_is_missing(tmp_path):
    from unittest.mock import MagicMock

    from orchestrator.audio_briefing import build_audio_script, build_tts_audio

    report = tmp_path / "2026-06-28.md"
    report.write_text("# Report\n\nSource-backed script.")
    script_result = build_audio_script(report, date="2026-06-28", user="ramsay")
    provider = MagicMock()

    result = build_tts_audio(
        script_result,
        dry_run=False,
        env={},
        tts_provider=provider,
    )

    provider.assert_not_called()
    assert result["status"] == "failed"
    assert result["mode"] == "provider"
    assert result["audio_bytes"] is None
    assert "MP_AUDIO_TTS_ENABLED" in result["error"]


def test_build_tts_audio_live_path_is_injectable_and_mocked(tmp_path):
    from unittest.mock import MagicMock

    from orchestrator.audio_briefing import build_audio_script, build_tts_audio

    report = tmp_path / "2026-06-28.md"
    report.write_text("# Report\n\nSource-backed script.")
    script_result = build_audio_script(report, date="2026-06-28", user="ramsay")
    provider = MagicMock(
        return_value={
            "audio_bytes": b"fixture mp3 bytes",
            "audio_format": "mp3",
            "duration_seconds": 12.5,
            "provider_request_id": "req_fixture",
        }
    )

    result = build_tts_audio(
        script_result,
        dry_run=False,
        env={
            "MP_AUDIO_TTS_ENABLED": "true",
            "MP_AUDIO_TTS_PROVIDER": "openai",
            "MP_AUDIO_TTS_MODEL": "fixture-model",
            "MP_AUDIO_TTS_VOICE": "fixture-voice",
        },
        tts_provider=provider,
    )

    provider.assert_called_once()
    script_arg, config_arg = provider.call_args.args
    assert script_arg == script_result["script"]
    assert config_arg.provider == "openai"
    assert config_arg.model == "fixture-model"
    assert config_arg.voice == "fixture-voice"
    assert result["status"] == "ready"
    assert result["mode"] == "provider"
    assert result["audio_bytes"] == b"fixture mp3 bytes"
    assert result["metadata"]["provider"] == "openai"
    assert result["metadata"]["model"] == "fixture-model"
    assert result["metadata"]["voice"] == "fixture-voice"
    assert result["metadata"]["audio_placeholder"] is False
    assert result["metadata"]["audio_hash"].startswith("sha256:")
    assert result["metadata"]["provider_request_id"] == "req_fixture"


def test_build_tts_audio_live_path_fails_closed_without_adapter(tmp_path):
    from orchestrator.audio_briefing import build_audio_script, build_tts_audio

    report = tmp_path / "2026-06-28.md"
    report.write_text("# Report\n\nSource-backed script.")
    script_result = build_audio_script(report, date="2026-06-28", user="ramsay")

    result = build_tts_audio(
        script_result,
        dry_run=False,
        env={
            "MP_AUDIO_TTS_ENABLED": "true",
            "MP_AUDIO_TTS_PROVIDER": "openai",
        },
    )

    assert result["status"] == "failed"
    assert result["audio_bytes"] is None
    assert "adapter" in result["error"].lower()


def test_write_audio_artifacts_writes_audio_transcript_metadata_and_provenance(tmp_path):
    from unittest.mock import MagicMock

    from orchestrator.audio_briefing import (
        build_audio_script,
        build_tts_audio,
        write_audio_artifacts,
    )

    report = tmp_path / "reports" / "ramsay" / "2026-06-28.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        """# MindPattern Research Agent - June 28, 2026

Source-backed story with [primary evidence](https://example.com/source).
""",
    )
    script_result = build_audio_script(report, date="2026-06-28", user="ramsay")
    tts_result = build_tts_audio(
        script_result,
        dry_run=False,
        env={
            "MP_AUDIO_TTS_ENABLED": "true",
            "MP_AUDIO_TTS_PROVIDER": "openai",
            "MP_AUDIO_TTS_MODEL": "fixture-model",
            "MP_AUDIO_TTS_VOICE": "fixture-voice",
        },
        tts_provider=MagicMock(
            return_value={
                "audio_bytes": b"fixture mp3 bytes",
                "audio_format": "mp3",
                "duration_seconds": 9.5,
                "provider_request_id": "req_fixture",
            }
        ),
    )

    result = write_audio_artifacts(
        tts_result,
        reports_root=tmp_path / "reports",
        generated_at="2026-06-28T12:00:00+00:00",
    )

    assert result["status"] == "ready"
    assert result["paths"]["audio"].read_bytes() == b"fixture mp3 bytes"
    transcript = result["paths"]["transcript"].read_text()
    metadata = json.loads(result["paths"]["metadata"].read_text())
    provenance = json.loads(result["paths"]["provenance"].read_text())

    assert "Source notes" in transcript
    assert "https://example.com/source" in transcript
    assert metadata["generated_at"] == "2026-06-28T12:00:00+00:00"
    assert metadata["source_report_hash"] == script_result["source_report_hash"]
    assert metadata["script_hash"] == script_result["script_hash"]
    assert metadata["model"] == "fixture-model"
    assert metadata["voice"] == "fixture-voice"
    assert metadata["source_count"] == 1
    assert metadata["has_audio_file"] is True
    assert "AI-generated audio" in metadata["labels"]
    assert provenance["tts"]["provider"] == "openai"
    assert provenance["tts"]["model"] == "fixture-model"
    assert provenance["tts"]["voice"] == "fixture-voice"
    assert provenance["source_notes"][0]["url"] == "https://example.com/source"


def test_write_audio_artifacts_logs_trace_statuses(tmp_path):
    from orchestrator.audio_briefing import (
        build_audio_script,
        build_tts_audio,
        write_audio_artifacts,
    )
    from orchestrator.traces_db import init_db

    traces_conn = init_db(tmp_path / "traces.db")
    ready_report = tmp_path / "ready.md"
    ready_report.write_text("# Report\n\nReady story.")
    degraded_report = tmp_path / "degraded.md"
    degraded_report.write_text(
        """> Degraded issue notice: source diversity weak.

# Report

Degraded story.
""",
    )

    ready = build_tts_audio(
        build_audio_script(ready_report, date="2026-06-28", user="ramsay"),
        dry_run=True,
    )
    degraded = build_tts_audio(
        build_audio_script(degraded_report, date="2026-06-28", user="ramsay"),
        dry_run=True,
    )
    failed = build_tts_audio(
        build_audio_script(tmp_path / "missing.md", date="2026-06-28", user="ramsay"),
        dry_run=True,
    )

    for index, result in enumerate([ready, degraded, failed], start=1):
        write_audio_artifacts(
            result,
            reports_root=tmp_path / "reports",
            traces_conn=traces_conn,
            pipeline_run_id=f"audio-test-{index}",
            generated_at=f"2026-06-28T12:00:0{index}+00:00",
        )

    rows = traces_conn.execute(
        "SELECT pipeline_run_id, event_type, payload FROM events ORDER BY id"
    ).fetchall()
    traces_conn.close()

    assert [row["event_type"] for row in rows] == [
        "audio_briefing_artifact",
        "audio_briefing_artifact",
        "audio_briefing_artifact",
    ]
    payloads = [json.loads(row["payload"]) for row in rows]
    assert [payload["status"] for payload in payloads] == ["ready", "degraded", "failed"]
    assert [payload["pipeline_artifact"] for payload in payloads] == [
        "audio_briefing",
        "audio_briefing",
        "audio_briefing",
    ]
    assert all("script_hash" in payload for payload in payloads)


def test_audio_artifact_paths_are_safe_and_gitignored(tmp_path):
    import subprocess

    from orchestrator.audio_briefing import audio_artifact_paths

    paths = audio_artifact_paths(
        date="2026-06-28",
        user="ramsay",
        reports_root=tmp_path / "reports",
    )

    assert paths["audio"] == tmp_path / "reports" / "ramsay" / "audio" / "2026-06-28.mp3"
    for kwargs in (
        {"date": "../../users", "user": "ramsay"},
        {"date": "2026-06-28", "user": "../ramsay"},
    ):
        try:
            audio_artifact_paths(reports_root=tmp_path / "reports", **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe audio artifact path was accepted")

    check = subprocess.run(
        ["git", "check-ignore", "reports/ramsay/audio/2026-06-28.mp3"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0


def test_audio_script_module_has_no_provider_network_or_runner_imports():
    source = Path("orchestrator/audio_briefing.py").read_text()
    tree = ast.parse(source)
    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)

    forbidden_imports = {
        "requests",
        "openai",
        "slack_bot",
        "orchestrator.runner",
        "orchestrator.newsletter",
        "social.posting",
    }
    forbidden_call_markers = {
        "send_newsletter",
        "chat.postMessage",
        "text_to_speech",
        "audio.speech",
        "generate_video",
        "flyctl",
    }

    assert imports.isdisjoint(forbidden_imports)
    for marker in forbidden_call_markers:
        assert marker not in source
