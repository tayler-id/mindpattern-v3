---
type: index
date: 2026-03-15
tags: [index, people]
---

# People

Notable people encountered in research. Tracks their affiliations, expertise, and mentions across runs.

```dataview
LIST FROM "people"
WHERE type = "person"
SORT file.mtime DESC
LIMIT 30
```
