"""Report validation and newsletter email delivery via Resend API.

Ported from v2 with enhancements:
- HTML rendering via markdown2 (sends both HTML and plain text)
- Uses requests with timeout and retry logic instead of urllib
- Traces integration via optional traces_conn parameter
"""

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import markdown2
import requests


@dataclass
class ValidationResult:
    path: Path
    original_bytes: int
    final_bytes: int
    junk_lines_stripped: int
    backup_restored: bool


@dataclass
class SendResult:
    success: bool
    resend_id: str | None = None
    error: str | None = None


# ── Traces helpers (thin wrappers to avoid hard import) ──────────────────


def _trace_start(traces_conn, pipeline_run_id: str, phase: str) -> str | None:
    """Start a traces agent_run if connection is available. Returns agent_run_id."""
    if not traces_conn or not pipeline_run_id:
        return None
    from datetime import datetime, timezone
    agent_run_id = f"{pipeline_run_id}/{phase}"
    now = datetime.now(timezone.utc).isoformat()
    traces_conn.execute(
        "INSERT OR IGNORE INTO agent_runs (id, pipeline_run_id, agent_name, status, started_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (agent_run_id, pipeline_run_id, phase, "running", now),
    )
    traces_conn.commit()
    return agent_run_id


def _trace_end(
    traces_conn,
    agent_run_id: str | None,
    status: str,
    *,
    output: str | None = None,
    error: str | None = None,
    latency_ms: int = 0,
):
    """Complete a traces agent_run."""
    if not traces_conn or not agent_run_id:
        return
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    truncated = output[:10_240] if output and len(output) > 10_240 else output
    traces_conn.execute(
        "UPDATE agent_runs SET status=?, completed_at=?, output=?, error=?, latency_ms=? WHERE id=?",
        (status, now, truncated, error, latency_ms, agent_run_id),
    )
    traces_conn.commit()


def _trace_event(traces_conn, pipeline_run_id: str | None, event_type: str, payload: str):
    """Log an event to traces.db."""
    if not traces_conn or not pipeline_run_id:
        return
    traces_conn.execute(
        "INSERT INTO events (pipeline_run_id, event_type, payload) VALUES (?, ?, ?)",
        (pipeline_run_id, event_type, payload),
    )
    traces_conn.commit()


# ── Public API ───────────────────────────────────────────────────────────


def validate_report(
    report_path: Path,
    *,
    traces_conn=None,
    pipeline_run_id: str | None = None,
) -> dict:
    """Strip junk lines before first heading. Restore backup if report is tiny.

    Returns a validation result dict with keys:
        path, original_bytes, final_bytes, junk_lines_stripped, backup_restored
    """
    start = time.monotonic()
    agent_run_id = _trace_start(traces_conn, pipeline_run_id, "report-validation")

    if not report_path.exists():
        result = ValidationResult(report_path, 0, 0, 0, False)
        _trace_end(
            traces_conn, agent_run_id, "failed",
            error=f"Report file not found: {report_path}",
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        return asdict(result)

    text = report_path.read_text()
    original_bytes = len(text.encode())
    lines = text.splitlines(keepends=True)

    # Find first line starting with '#'
    first_hash_idx = None
    for i, line in enumerate(lines):
        if line.startswith("#"):
            first_hash_idx = i
            break

    junk_lines_stripped = 0
    if first_hash_idx is not None and first_hash_idx > 0:
        junk_lines_stripped = first_hash_idx
        text = "".join(lines[first_hash_idx:])
        report_path.write_text(text)

    report_bytes = len(text.encode())

    # Backup/restore logic
    backup_path = report_path.with_suffix(".backup.md")
    backup_restored = False

    if backup_path.exists():
        backup_bytes = len(backup_path.read_bytes())
        if report_bytes < 1000 and backup_bytes > 1000:
            shutil.copy2(backup_path, report_path)
            backup_restored = True
            report_bytes = len(report_path.read_bytes())
            backup_path.unlink()
        else:
            # Report is fine — remove backup
            backup_path.unlink()

    result = ValidationResult(
        path=report_path,
        original_bytes=original_bytes,
        final_bytes=report_bytes,
        junk_lines_stripped=junk_lines_stripped,
        backup_restored=backup_restored,
    )

    _trace_end(
        traces_conn, agent_run_id, "completed",
        output=json.dumps({
            "junk_lines_stripped": junk_lines_stripped,
            "backup_restored": backup_restored,
            "original_bytes": original_bytes,
            "final_bytes": report_bytes,
        }),
        latency_ms=int((time.monotonic() - start) * 1000),
    )

    return asdict(result)


def render_html(markdown_text: str) -> str:
    """Convert markdown to HTML email using markdown2.

    Uses extras: tables, fenced-code-blocks, header-ids.
    Wraps output in a basic email template with -apple-system font stack
    and max-width 700px.
    """
    body_html = markdown2.markdown(
        markdown_text,
        extras=["tables", "fenced-code-blocks", "header-ids"],
    )

    return f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #1a1a1a;
    max-width: 700px;
    margin: 0 auto;
    padding: 20px;
    background-color: #ffffff;
  }}
  h1, h2, h3 {{ color: #111; margin-top: 1.5em; }}
  h1 {{ font-size: 1.5em; border-bottom: 2px solid #eee; padding-bottom: 0.3em; }}
  h2 {{ font-size: 1.25em; border-bottom: 1px solid #eee; padding-bottom: 0.2em; }}
  a {{ color: #0066cc; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  code {{
    background: #f5f5f5;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.9em;
  }}
  pre {{
    background: #f5f5f5;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
  }}
  pre code {{ background: none; padding: 0; }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
  }}
  th, td {{
    border: 1px solid #ddd;
    padding: 8px 12px;
    text-align: left;
  }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  blockquote {{
    border-left: 3px solid #ddd;
    margin: 1em 0;
    padding: 0.5em 1em;
    color: #555;
  }}
  hr {{ border: none; border-top: 1px solid #eee; margin: 2em 0; }}
  ul, ol {{ padding-left: 1.5em; }}
  li {{ margin-bottom: 0.3em; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""


def keychain_lookup(service_name: str) -> str | None:
    """Look up a password from macOS Keychain via security CLI.

    Returns the password string or None if not found.
    """
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service_name, "-w"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None


def send_newsletter(
    report_path: Path,
    user_config: dict,
    date_str: str,
    *,
    traces_conn=None,
    pipeline_run_id: str | None = None,
) -> dict:
    """Send newsletter email via Resend API using requests.

    Sends BOTH HTML and plain text versions. Uses retry logic with
    exponential backoff (max 3 attempts).

    Returns dict with keys: success, resend_id, error.
    """
    start = time.monotonic()
    agent_run_id = _trace_start(traces_conn, pipeline_run_id, "newsletter-sending")

    api_key = keychain_lookup("resend-api-key")
    if not api_key:
        result = SendResult(False, error="No resend-api-key found in Keychain")
        _trace_end(
            traces_conn, agent_run_id, "failed",
            error=result.error,
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        return asdict(result)

    # Read report content
    if not report_path.exists():
        result = SendResult(False, error=f"Report file not found: {report_path}")
        _trace_end(
            traces_conn, agent_run_id, "failed",
            error=result.error,
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        return asdict(result)

    report_content = report_path.read_text()
    html_content = render_html(report_content)

    # Build email payload
    newsletter_title = user_config.get("newsletter_title", "Daily Research")
    reply_to = user_config.get("reply_to", "")
    user_email = user_config.get("email", "")

    payload = {
        "from": f"{newsletter_title} <{reply_to}>",
        "to": [user_email],
        "subject": f"{newsletter_title} — {date_str}",
        "html": html_content,
        "text": report_content,
        "reply_to": [reply_to],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "mindpattern/3.0",
    }

    # Retry with exponential backoff (max 3 attempts)
    last_error = None
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            resp_data = resp.json()

            resend_id = resp_data.get("id")
            if resend_id:
                result = SendResult(True, resend_id=resend_id)
                break
            else:
                last_error = f"No id in response: {resp_data}"
                result = SendResult(False, error=last_error)
                break  # Don't retry on unexpected response shape

        except requests.exceptions.HTTPError as e:
            body = e.response.text if e.response is not None else str(e)
            status_code = e.response.status_code if e.response is not None else 0
            last_error = f"HTTP {status_code}: {body}"

            # Don't retry on 4xx client errors (except 429 rate limit)
            if e.response is not None and 400 <= status_code < 500 and status_code != 429:
                result = SendResult(False, error=last_error)
                break

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_error = str(e)

        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            last_error = str(e)
            result = SendResult(False, error=last_error)
            break  # Don't retry on decode errors

        # Exponential backoff: 1s, 2s
        if attempt < 2:
            time.sleep(2 ** attempt)
    else:
        # All retries exhausted
        result = SendResult(False, error=f"All 3 attempts failed. Last error: {last_error}")

    latency_ms = int((time.monotonic() - start) * 1000)

    # Log trace event
    _trace_event(
        traces_conn, pipeline_run_id,
        "newsletter_sent" if result.success else "newsletter_failed",
        json.dumps({
            "to": user_email,
            "success": result.success,
            "resend_id": result.resend_id,
            "error": result.error,
        }),
    )

    # Complete agent run
    _trace_end(
        traces_conn, agent_run_id,
        "completed" if result.success else "failed",
        error=result.error,
        latency_ms=latency_ms,
    )

    return asdict(result)


if __name__ == "__main__":
    import tempfile

    # --- AC #1: Report validation — junk line stripping ---
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("Some junk line\nAnother junk\n# Real Report\n\nContent here.\n")
        tmp_path = Path(f.name)

    result = validate_report(tmp_path)
    assert result["junk_lines_stripped"] == 2, f"Expected 2, got {result['junk_lines_stripped']}"
    content = tmp_path.read_text()
    assert content.startswith("# Real Report"), f"Got: {content[:50]}"
    tmp_path.unlink()
    print("AC #1a: Junk line stripping verified")

    # --- AC #1: No junk lines ---
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Clean Report\n\nContent.\n")
        tmp_path = Path(f.name)

    result = validate_report(tmp_path)
    assert result["junk_lines_stripped"] == 0
    tmp_path.unlink()
    print("AC #1b: No junk lines — no stripping")

    # --- AC #1: Backup/restore with undersized report ---
    tmp_dir = Path(tempfile.mkdtemp())
    report = tmp_dir / "2026-03-14.md"
    backup = tmp_dir / "2026-03-14.backup.md"
    report.write_text("tiny")
    backup.write_text("# Full Report\n\n" + "x" * 2000)

    result = validate_report(report)
    assert result["backup_restored"], "Expected backup to be restored"
    assert result["final_bytes"] > 1000
    print("AC #1c: Backup/restore for undersized report verified")

    # --- AC #1: Backup deleted when report is fine ---
    report.write_text("# Good Report\n\n" + "x" * 2000)
    backup.write_text("# Old Backup\n\n" + "y" * 2000)
    result = validate_report(report)
    assert not result["backup_restored"]
    assert not backup.exists()
    print("AC #1d: Backup cleanup verified")
    shutil.rmtree(tmp_dir)

    # --- AC #2: HTML rendering ---
    html = render_html("# Hello\n\nSome **bold** text.\n\n| A | B |\n|---|---|\n| 1 | 2 |")
    assert "-apple-system" in html, "Expected -apple-system font"
    assert "max-width: 700px" in html, "Expected max-width"
    assert "<table>" in html, "Expected table rendering"
    assert "<strong>bold</strong>" in html, "Expected bold"
    print("AC #2: HTML rendering verified")

    # --- AC #3: Keychain lookup ---
    kc = keychain_lookup("nonexistent-test-key-12345")
    assert kc is None
    print("AC #3: Keychain lookup returns None for missing key")

    # --- AC #4: Send newsletter (graceful failure) ---
    mock_config = {
        "email": "test@example.com",
        "newsletter_title": "Test Newsletter",
        "reply_to": "feedback@test.com",
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Test Report\n\nContent.\n")
        test_report = Path(f.name)
    send_result = send_newsletter(test_report, mock_config, "2026-03-14")
    assert not send_result["success"]
    assert send_result["error"] is not None
    test_report.unlink()
    print(f"AC #4: Newsletter send failed gracefully ({send_result['error'][:60]}...)")

    print("\nAll newsletter.py checks passed.")
