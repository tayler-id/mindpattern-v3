---
type: index
date: 2026-03-15
tags: [index, sources]
---

# Sources

Tracked sources with reliability scores and signal history. Agents consult this to prioritize where to look and how much to trust what they find.

```dataview
LIST FROM "sources"
WHERE type = "source"
SORT file.mtime DESC
LIMIT 30
```
