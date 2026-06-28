import ast
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
