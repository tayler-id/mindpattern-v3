# orchestrator/sync.py

> Fly.io sync. Bundles memory.db, traces.db and reports into a tar.gz, POSTs it to the app over HTTPS, falls back to flyctl SFTP, restarts the app, then warms the public site.

## What It Does

WAL checkpoint both DBs, bundle, upload, extract on the volume, restart the Fly app, warm the site.

The preferred path is `upload_bundle_http`, a POST to `/api/sync/bundle` that the app checks by sha256 and extracts itself (`dashboard/routes/sync_upload.py`). The SFTP path runs only when that fails. After the restart, `warm_public_site` purges and re-crawls the day's changed paths on mindpattern.ai. The operator runbook, with the volume budget and the cache layers a reader's click goes through, is `docs/runbooks/fly-sync-and-site-cache.md`.

## Key Functions

Bundle, upload, restart and warm.

- `sync_to_fly(user_id, data_dir, app_name, traces_conn)` orchestrates the upload and every fallback
- `create_bundle(user_id, data_dir, reports_dir, date_str)` builds the tar.gz
- `upload_bundle_http(bundle_path, user_id)` is the HTTPS path, 3 attempts
- `upload_bundle` and `upload_bundle_chunked` are the SFTP fallback
- `restart_app(app_name)` restarts the machine so the dashboard reopens the new DB files
- `warm_public_site(date, scope)` purges and crawls the site after a publish or deploy
- `write_synced_marker(date_str)` writes `/tmp/mindpattern-synced-<date>`, which stops the launchd retries

## Depends On

flyctl for the SFTP fallback and the restart. Called by [[orchestrator/runner]] `_phase_sync` and by `run.py --sync-only`.

## Known Fragile Points

Where a sync can fail or run slowly.

- A full Fly volume breaks every path at once. HTTPS dies with `BrokenPipeError` because the app spools the bundle to `/data` first, and SFTP stops memory.db at the old file's exact byte count. Check `df -h /data` before anything else. This cost six days of syncs, 2026-10-17 to 10-22.
- `dashboard/site_cache.py` refuses cache writes that would leave less than 1 GiB free, and a landed HTTPS sync deletes the entity, finding and related cache entries it just invalidated. The SFTP path does not delete them.
- `warm_public_site` after a sync covers only that day's paths. A sync that lands after missed days leaves the missed days' pages unwarmed.
- WAL checkpoint failures log a warning and the sync continues
- Hardcoded timeouts (600s HTTPS, 300s SFTP upload, 60s SSH)

## Last Modified By Harness

Never. Created 2026-04-01, rewritten by hand 2026-10-22.
