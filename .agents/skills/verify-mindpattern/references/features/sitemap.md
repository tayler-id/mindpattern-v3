# Discover published story URLs

## Sub-features

- Enumerate published stories for a crawler.
- Exclude draft and rejected story artifacts.

## How to get to it (user POV)

The public site's sitemap builder requests `GET /api/site/sitemap`. Search crawlers consume the frontend's resulting sitemap.

## Driving it with verification

```sh
.venv/bin/python3 -m verification verify sitemap
.venv/bin/python3 -m verification request '/api/site/sitemap?user=ramsay'
```

Prove that `verification-story` appears and unpublished artifacts do not. Save the response with its exact expected story set.

Sources: [sitemap endpoint](../../../../../dashboard/routes/api.py), [sitemap tests](../../../../../tests/test_site_content_api.py).

## Gotchas

The fixture covers story discovery. Empty entity, source, or briefing collections do not prove those sitemap branches. This API check does not prove frontend XML, canonical metadata, robots rules, or search indexing.
