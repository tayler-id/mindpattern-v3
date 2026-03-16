---
type: index
date: 2026-03-15
tags: [index, topics]
---

# Topics

Evergreen topic files that accumulate knowledge across runs. Each topic tracks developments, key players, and the user's perspective over time.

```dataview
LIST FROM "topics"
WHERE type = "topic"
SORT file.mtime DESC
LIMIT 30
```
