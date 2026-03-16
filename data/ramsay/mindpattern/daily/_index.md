---
type: index
date: 2026-03-15
tags: [index, daily]
---

# Daily Research Reports

Each day's research output is stored here as a single note. Agents read recent dailies for continuity and deduplication.

```dataview
LIST FROM "daily"
WHERE type = "daily"
SORT date DESC
LIMIT 30
```
