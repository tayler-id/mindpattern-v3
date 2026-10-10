# orchestrator/evaluator.py

> Newsletter quality scoring. No LLM. 6 dimensions, weighted composite 0.0-1.0.

## Dimensions & Weights

Six scores, weighted into `overall`.

| Dimension | Weight | What It Checks |
|-----------|--------|----------------|
| coverage | 0.25 | High-importance findings represented (50% title word match) |
| dedup | 0.20 | No duplicate sections (60% word overlap threshold) |
| sources | 0.15 | All sections have URLs |
| actionability | 0.15 | "Why it matters", action items, skills section |
| length | 0.10 | Inside `newsletter.length.issue_words` in `policies/editorial.json` (scales down outside) |
| topic_balance | 0.15 | Matches user preference weights |

## Key Class

`NewsletterEvaluator(db)` — takes memory.db connection. `evaluate(newsletter_text, agent_reports, user_preferences) -> dict`

## Depends On

Nothing external. Uses [[data/memory-db]] findings + preferences.

## Known Fragile Points

Where a score can be wrong.

- Coverage uses 50% word match — loose, can match wrong sections
- Section splitting by ## or # — breaks on code blocks with # characters
- Actionability scoring additive, clamped to 1.0 — early categories can crowd out later
- Stop words English-only
- Weights not configurable per user
- Sources scoring regression: dropped to 0.333 on security topics (Run 19, unresolved)

## Last Modified By Harness

Never — created 2026-04-01.
