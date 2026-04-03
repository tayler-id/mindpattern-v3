# orchestrator/evaluator.py

## Purpose
Post-synthesis newsletter quality evaluation. Scores newsletters on 6 dimensions, all deterministic (no LLM calls).

## API
- `NewsletterEvaluator(db)` — constructor takes a sqlite3 connection (used for similarity search)
- `evaluate(newsletter_text, agent_reports, user_preferences)` → dict with keys: coverage, dedup, sources, actionability, length, topic_balance, overall (all floats 0.0–1.0)

## Scoring Dimensions
- **coverage** — checks if high/critical importance agent report titles appear in newsletter (50% keyword match threshold)
- **dedup** — pairwise section overlap via keyword intersection (>60% overlap = duplicate)
- **sources** — fraction of sections containing URLs
- **actionability** — presence of "why it matters", action items, skills section, actionable bullet points (4 sub-checks, 0.3/0.3/0.2/0.2 weights)
- **length** — 1.0 if 3000-5000 words, scaled down outside (min 0.1)
- **topic_balance** — checks user preference topics appear in newsletter, weighted by preference weight. Negative-weight prefs excluded. Duplicates deduped.

## Composite
Weighted: coverage 0.25, dedup 0.20, sources 0.15, actionability 0.15, length 0.10, topic_balance 0.15. Clamped to [0.0, 1.0].

## Private Helpers (module-level)
- `_extract_significant_words(text)` — lowercase, no stop words, 3+ chars
- `_split_into_sections(text)` — splits by `##`/`#` headings into (heading, body) tuples

## Test Coverage
- `tests/test_evaluator.py` — 6 tests covering length, dedup, sources, evaluate(), and empty input edge case

## Known Issues
- Sources score regression on security topics (0.333, Run 19) — structural issue, not a code bug
