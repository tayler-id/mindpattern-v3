# Fly sync and the site cache

The daily SYNC phase puts the day's data on the Fly volume. The public site at mindpattern.ai renders from that volume through four cache layers. This page covers how a reader's click reaches the data, what empties each layer, the volume's space budget, and what to do when the sync fails or a page spins.

Code: `orchestrator/sync.py` (client), `dashboard/routes/sync_upload.py` (upload endpoint), `dashboard/site_cache.py` (disk cache), `dashboard/routes/api.py` (`_cached_offload`, `_data_fingerprint`).

## What a click goes through

A request for `/s/<slug>`, `/e/<slug>`, `/f/<id>` or `/source/<domain>` on mindpattern.ai checks these in order and stops at the first hit.

1. **Vercel ISR.** Each page has a day-long TTL. After it expires, Vercel serves the old copy (`x-vercel-cache: STALE`) and re-renders in the background, so a reader only waits on a page Vercel has never rendered (`MISS`). A Vercel deploy drops the whole ISR cache.
2. **Backend memory cache.** `_PUBLIC_RESPONSE_CACHE` in `api.py`, 4,096 entries, keyed by the data fingerprint. Any restart empties it. The fingerprint is the newest mtime across the story trees and memory.db, so every sync moves it.
3. **Disk cache on the volume.** `/data/ramsay/site-cache/{stories,entities,findings,related}/`, one JSON file per slug, written the first time anything requests that slug. Story entries key on their own source file and survive a sync. Entity, finding and related entries key on the data fingerprint, so a sync turns every one of them into a permanent miss. The upload endpoint deletes those three directories after it extracts a bundle.
4. **Live compute.** Reads memory.db and the story JSON on the volume.

Measured 2026-10-22 after a sync, serial requests:

| Request | Time |
|---|---|
| Story page, Vercel `HIT` or `STALE` | 0.18 to 0.5s |
| Story page, Vercel `MISS` (cold render) | 0.8 to 1.7s |
| Entity or source page, Vercel `HIT` or `REVALIDATED` | 0.23 to 0.67s |
| Backend `/api/stories/<slug>`, no disk entry | 1.2 to 5.0s |
| Backend `/api/stories/<slug>`, memory or disk hit | 0.25 to 0.37s |

The story disk backfill at boot is off (`MP_WARMUP_BACKFILL_MINUTES=0` in fly.toml) because it held the event loop for 20 minutes on 2026-08-27. Disk entries fill one request at a time instead.

## What the sync does to the caches

`run.py` runs SYNC after DELIVER. `_phase_sync` calls `sync_to_fly`, which tries these in order:

1. POST the bundle to `/api/sync/bundle`. The endpoint spools it to a temp file on `/data`, checks the sha256, extracts it, and deletes the stale entity, finding and related disk entries.
2. If that fails, `flyctl ssh sftp` the bundle, falling back to 1 MB chunks. Then extract over SSH.
3. If the extract fails, SFTP the reports and both databases one file at a time and check each landed at its local size.

On success the runner restarts the app, which empties the memory cache, then calls `warm_public_site(scope="changed")`. That purges and re-crawls up to 200 of the day's paths (stories, sources, arcs, entities, findings) in waves of 10 with a 10-minute budget. On 2026-10-22 it warmed 126 paths in four minutes with none failing.

The warm covers the current day only. A sync that lands after missed days leaves the missed days' new pages for readers to render cold. To warm one by hand, run this once per missed date, never two at once:

```sh
.venv/bin/python3 -m orchestrator.sync warm --date 2026-10-20
```

## Volume budget

The volume is `mindpattern_data`, 3 GB, region sjc. On 2026-10-22, before the fix:

| Path | Size |
|---|---|
| `/data/ramsay/site-cache/related` | 823 MB, 28,635 files |
| `/data/ramsay/site-cache/entities` | 770 MB, 35,046 files |
| `/data/ramsay/site-cache/findings` | 576 MB, 28,635 files |
| `/data/ramsay/site-cache/stories` | 204 MB, 5,996 files |
| `/data/site_events.db` | 220 MB |
| `/data/reports` | 142 MB |
| `/data/ramsay/memory.db` | 118 MB |
| `/data/ramsay/traces.db` | 50 MB |
| `/data/uploads` | 36 MB |

A sync needs free space for the bundle (108 MB on 2026-10-22, 300 MB cap) before it can extract anything, and the SFTP fallback holds the chunks and the reassembled bundle at the same time. `site_cache.write_body` refuses any write that would leave less than `MIN_FREE_BYTES` (1 GiB) free, and logs `not caching <slug>, the volume is down to its ... sync reserve`. If that line shows up in `flyctl logs`, the cache has hit its floor and the volume needs attention, but the sync still has its room.

Crawlers decide how fast the cache grows. By Oct 22, requests had reached 28,635 of the 30,745 findings, and each one wrote a finding file and a related file. Most cache files were last written between Oct 14 and 19. Right after clearing the cache on 2026-10-22, it refilled at about 50 files every 20 seconds.

## When the sync fails

The Slack alert reads `Fly sync failed for ramsay` followed by the last error. Check free space first. Every path fails on a full volume, and the errors don't say so.

```sh
flyctl ssh console -a mindpattern -C "df -h /data"
```

These lines in `reports/launchd-stderr.log` mean the volume is full:

- `HTTP sync upload attempt 1 failed: BrokenPipeError`. The endpoint died writing its temp file and dropped the connection mid-upload.
- `Remote bundle size 450560 != local 108057433` and `bundle truncated after retry (remote -1, ...)`. SFTP stopped when the disk did.
- `SFTP /data/ramsay/memory.db landed at 123539456 bytes, expected 127320064`. The upload overwrote the old file's blocks and stopped at the old file's exact size, because growing it needed blocks the volume didn't have.

To recover a full volume:

```sh
# 1. Delete the cache entries the next sync would invalidate anyway. Run it
#    twice if rm reports "Directory not empty". The live app keeps writing.
flyctl ssh console -a mindpattern -C "sh -c 'cd /data/ramsay/site-cache && rm -rf entities findings related && df -h /data'"

# 2. Rerun only the sync. It uploads, restarts the app, and warms today's paths.
.venv/bin/python3 run.py --skip-social --sync-only
```

Leave `site-cache/stories` alone. Those entries survive syncs, and losing them makes every archive story render cold.

If the volume is full and the cache is small, something else grew. Run `du -sh /data/* /data/ramsay/*` and check before extending the volume (`flyctl volumes extend`), which can't be undone.

## When a page spins

Find which layer is slow before changing anything.

```sh
curl -s -o /dev/null -D - -w '%{http_code} %{time_total}s\n' https://mindpattern.ai/s/<slug> | grep -i 'x-vercel-cache\|^age\|s$'
curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' https://mindpattern.fly.dev/api/stories/<slug>
curl -s https://mindpattern.fly.dev/api/warmup/status
```

- A Vercel `HIT` or `STALE` that is slow points at Vercel, not the backend.
- A `MISS` over 2 seconds with a slow backend call means the backend is cold. Check whether a restart or deploy just happened and whether `/api/warmup/status` still says `running`.
- A backend 502 right after a sync or deploy is the restart. It clears once `/healthz` answers again.
- A 404 for a story that exists locally means the bundle with that date never landed. Check the sync.

Never measure or warm while another crawl or a sync is running. The box has shared CPUs, and concurrent crawls have wedged it before.

## Incident, 2026-10-17 to 10-22

Crawler requests filled the 3 GB volume through the disk cache. With 0 bytes free, every sync failed for six days. That was the six daily runs plus 47 launchd retries, each retry spending about 20 minutes in SFTP fallbacks. The dashboard never received a complete memory.db after Oct 16. Vercel still held copies of Oct 17 to 19 stories rendered before the recovery, so some story files did reach the volume on failed days. Recovery took one `rm` of the three fingerprint-keyed cache directories (2.2 GB) and one sync-only run, whose HTTPS upload finished in 28 seconds. The fix added the 1 GiB floor on cache writes and the post-extract delete of invalidated entries.
