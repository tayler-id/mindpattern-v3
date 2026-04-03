# orchestrator/newsletter.py

> Report validation, HTML rendering, email delivery via Resend API.

## What It Does

Strips junk lines from markdown reports, restores from .backup.md if report is tiny (<1000 bytes), renders HTML via markdown2, sends email with retry (3 attempts, exponential backoff).

## Key Functions

- `validate_report(report_path, traces_conn, pipeline_run_id)` — strips junk, restores backup if needed
- `render_html(markdown_text)` — markdown2 with tables, fenced-code, header-ids
- `send_newsletter(report_path, user_config, date_str, report_content, traces_conn, pipeline_run_id)` — Resend API with retry
- `keychain_lookup(service_name)` — macOS Keychain password lookup

## Depends On

markdown2, requests. Logs to [[data/traces-db]]. Called by [[orchestrator/runner]] _phase_deliver.

## Known Fragile Points

- Backup detection uses 1000 byte threshold — off-by-one possible
- Keychain lookup macOS-only — no fallback on other OS
- Retry has no jitter — thundering herd risk
- Email subject not unique per day — multiple sends have identical subjects

## Last Modified By Harness

Never — created 2026-04-01.
