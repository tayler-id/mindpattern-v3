---
name: rabbit-hole-site-quality
description: Audit and improve the Rabbit Hole public experience across mindpattern-v3's content and API layer and mindpattern-rabbit-hole's Next.js frontend. Use for story grounding, copy lint, confidence gates, graph connectivity, API contracts, SEO/AEO/GEO metadata, analytics, performance, accessibility, or browser validation. Do not use for historical backfill, newsletter or social operations, or generic frontend work.
---

# Rabbit Hole Site Quality

Use current code, tests, runtime configuration, and live state before dated handoffs.

Bound broad audits before inspecting deeply. Unless the user explicitly asks for a full-corpus audit, sample at most three representative stories and three public routes, choose the smallest relevant test group, and stop when the evidence is sufficient to identify or rule out the requested failure. Report the sample and anything not covered.

## Select the surface

- For editorial quality, inspect `docs/specs/site-writer-rules.md`, `orchestrator/site_copy_lint.py`, `orchestrator/site_writer.py`, `orchestrator/site_critic.py`, and the site-story agents.
- For API and graph behavior, inspect `orchestrator/site_content*.py`, `orchestrator/site_graph.py`, `orchestrator/site_dossiers.py`, and `dashboard/routes/api.py`.
- For frontend quality, work in `/Users/taylerramsay/Projects/mindpattern-rabbit-hole` and inspect its design system, API client, analytics, metadata, sitemap, robots, JSON-LD, and route boundaries.

## Verify the backend

```sh
.venv/bin/python3 -m pytest tests/test_site_copy_lint.py tests/test_site_writer.py tests/test_site_critic.py tests/test_site_content_confidence.py -q
.venv/bin/python3 -m pytest tests/test_site_content_engine.py tests/test_site_content_api.py tests/test_site_graph_api.py tests/test_site_graph_read_model.py tests/test_site_related_paths.py tests/test_site_dossiers.py tests/test_api_contract.py tests/test_site_analytics.py -q
```

Use a temporary reports root for deterministic artifact smoke tests:

```sh
.venv/bin/python3 tools/site-content-dry-run.py --date <YYYY-MM-DD> --user ramsay --reports-root /private/tmp/mp-site-content-smoke
```

## Verify the frontend

Run lint, TypeScript checking, build, and then browser validation against the local backend. Keep deploys, provider calls, production indexing changes, and canonical report writes approval-bound.

Preserve these invariants: the copy floor is an editorial gate rather than an AI detector; public claims remain source-grounded and sanitized; internal machinery labels never leak; graph relationships remain evidence-backed; Spectrum remains the design source of truth; analytics stays privacy-safe and best-effort.
