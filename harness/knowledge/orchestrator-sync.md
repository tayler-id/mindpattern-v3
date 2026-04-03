# orchestrator/sync.py

> Fly.io sync. Bundles memory.db + traces.db + reports into tar.gz, uploads via flyctl SFTP.

## What It Does

WAL checkpoint both DBs, create tar.gz bundle, upload single file via SFTP, extract remotely, restart Fly app. Optimized from 30 connections to 1.

## Key Functions

- `sync_to_fly(user_id, data_dir, app_name, traces_conn)` — orchestrate full sync
- `create_bundle(user_id, data_dir, reports_dir, date_str)` — tar.gz with mirrored dirs
- `upload_bundle(bundle_path, remote_path, app_name)` — flyctl sftp, 5 min timeout
- `restart_app(app_name)` — flyctl machines restart

## Depends On

flyctl CLI, subprocess. Called by [[orchestrator/runner]] _phase_sync.

## Known Fragile Points

- SFTP error detection checks "bytes written" substring — fragile across flyctl versions
- Falls back to per-file SFTP on extraction failure — slow, defeats bundling
- WAL checkpoint failures logged as warnings, continues — may lose recent writes
- Hardcoded timeouts (300s upload, 60s SSH)
- No resume on interrupted upload

## Last Modified By Harness

Never — created 2026-04-01.
