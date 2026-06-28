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
