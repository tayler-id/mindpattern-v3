# dashboard: CampaignOS story identity and attribution

> The two mindpattern-v3 changes the CampaignOS pilot needed: an exact revision id per story (gate G4, PR #26) and campaign attribution on reader events (gate G5, PR #27).

## Story Identity

A story file answers to its stem without its own date folder's prefix, so `2026-07-12/foo.json` and `2026-07-12/2026-07-12-foo.json` are both `foo`. The memoized index in `dashboard/routes/api.py` keys files that way.

A slug that matches more than one file is refused everywhere: the story route, the disk cache, the warm-up, and the structured-issue fallback.

## Revision Endpoint

`GET /api/stories/{slug}/revision` returns the SHA-256 of the raw file bytes served at `/s/<slug>`. It answers 404 for an unknown or undated story and 409 with the matching files for an ambiguous slug.

## Attribution

`memory/events_db.py` adds `campaign_id` and `source_channel`, normalized safe ids, accepted only on story, source-click, subscribe, and share events. Columns are additive migrations, so the events table on the Fly volume keeps its rows.

`GET /api/site-analytics/campaigns` is the private aggregate view.

## Known Issues

Seven stories had a same-date duplicate pair, written by both the candidate writer and the issue writer. One file of each moved aside on 2026-10-02, and `write_issue_stories_for_date` now skips a unit whose candidate story exists under the bare slug. See [[issues/open]].

## Last Updated

2026-10-02. Merged into main with the models harness branch.
