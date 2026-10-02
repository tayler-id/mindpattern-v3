# Search published stories

## Sub-features

- Search title, summary, and dek text.
- Return grouped story results.
- Return no matches for absent terms.
- Exclude unpublished stories.

## How to get to it (user POV)

A reader enters terms into site search. The story group comes from `GET /api/search/site` with `types=stories`.

## Driving it with verification

```sh
.venv/bin/python3 -m verification verify story-search
.venv/bin/python3 -m verification request '/api/search/site?q=verification&types=stories&user=ramsay'
```

Prove that matching input returns the seeded published story, absent terms return an empty stories group, and the draft is excluded. Preserve the input query with each response.

Sources: [search route](../../../../../dashboard/routes/site_search.py), [search tests](../../../../../tests/test_search_site.py).

## Gotchas

This scenario covers story text search. Findings search can load an embedding model and is outside this offline driver. Date filters, pagination, take-only search, entity groups, and source groups need their own fixtures and assertions before claiming coverage.
