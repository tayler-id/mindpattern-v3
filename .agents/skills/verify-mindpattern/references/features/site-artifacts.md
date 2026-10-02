# Inspect public run and corpus summaries

## Sub-features

- Read the site-content result for a date.
- Read corpus counts for a date.
- Remove private fields from public responses.
- Distinguish a missing run from an invalid date.

## How to get to it (user POV)

A client requests `GET /api/site/runs/<date>` or `GET /api/site/corpus/<date>`. These endpoints describe generated content. They do not start a research run.

## Driving it with verification

```sh
.venv/bin/python3 -m verification verify site-artifacts
.venv/bin/python3 -m verification request '/api/site/runs/2026-07-01?user=ramsay'
.venv/bin/python3 -m verification request '/api/site/corpus/2026-07-01?user=ramsay'
```

Prove that the expected counts survive serialization and synthetic private markers do not. Check the missing-date response and rejection of an invalid date. Save complete response bodies for the synthetic fixture.

Sources: [API routes](../../../../../dashboard/routes/api.py), [artifact tests](../../../../../tests/test_site_content_api.py).

## Gotchas

Run and corpus summaries are different from structured newsletter issues. This scenario does not prove `GET /api/issues/<date>/structured` or execute the content pipeline. Counts describe the fixture only.
