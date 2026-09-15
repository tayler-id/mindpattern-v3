# Read published stories

## Sub-features

- Browse the published story list.
- Open a story and inspect its content, source references, and provenance.
- Keep draft and invalid published artifacts out of reader responses.
- Return 404 for an unavailable story.

## How to get to it (user POV)

Rabbit Hole readers open a story card and follow its `/s/<slug>` URL. The frontend obtains the list from `GET /api/stories` and the detail from `GET /api/stories/<slug>`.

## Driving it with verification

```sh
.venv/bin/python3 -m verification verify stories
.venv/bin/python3 -m verification request '/api/stories?user=ramsay&limit=10'
.venv/bin/python3 -m verification request '/api/stories/verification-story?user=ramsay'
```

The synthetic published slug is `verification-story`. Prove that it is visible, that its detail includes its evidence, and that rejected artifacts remain unavailable. Preserve the list and detail responses with the assertions.

Sources: [API routes](../../../../../dashboard/routes/api.py), [public story tests](../../../../../tests/test_site_content_api.py).

## Gotchas

Story reads can populate disk caches. The CLI keeps those writes inside scratch state. This scenario does not assess live editorial quality, graph completeness, related-story ranking, or the frontend layout.
