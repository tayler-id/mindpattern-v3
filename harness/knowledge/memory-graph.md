# memory/graph.py — Entity Graph Operations

> Knowledge graph storage and traversal using SQLite recursive CTEs.

## API

| Function | Purpose |
|---|---|
| `store_relationship(db, entity_a, relationship, entity_b, ...)` | Insert an edge into entity_graph. Returns row ID. |
| `query_entity(db, name)` | Get all relationships for an entity (both directions). Returns dict with relationships list and findings_count. |
| `find_path(db, entity_a, entity_b, max_depth=4)` | Shortest path via recursive CTE. Returns list of {entity, relationship} dicts or None. |
| `related_entities(db, name, depth=1)` | N-hop neighborhood search. Returns list of {entity, type, depth} dicts sorted by depth. |
| `entity_stats(db)` | Graph-wide stats: total entities, total relationships, top 20 entities by connection count. |

## Schema

All operations use the `entity_graph` table:
- `id` INTEGER PRIMARY KEY
- `entity_a`, `entity_a_type`, `relationship`, `entity_b`, `entity_b_type`
- `finding_id` (optional FK to findings)
- `created_at` ISO timestamp

## Known Behaviors

- **Duplicates allowed**: `store_relationship` does not deduplicate. Calling it twice with the same args creates two rows.
- **Bidirectional queries**: `query_entity` and `related_entities` treat edges as undirected (UNION ALL on both directions).
- **Path reconstruction**: `find_path` uses the `visited` column (pipe-delimited entity names) to reconstruct the full path, then looks up relationships per hop.
- **No cascade deletes**: Removing a finding does not remove its entity_graph rows.

## Test Coverage

`tests/test_graph.py` — 16 tests covering:
- Store relationship (basic insert, with finding_id, duplicate handling)
- Query entity (both directions, empty graph, findings count)
- Related entities (depth 1, depth 2, no neighbors)
- Find path (direct, multi-hop, no path, max_depth limit)
- Entity stats (empty graph, populated, ordering)

## Known Issues

- `entity_graph` table must be created by `memory/db.py._init_schema()`. If missing, all operations fail with `sqlite3.OperationalError`.
- No indexes on `entity_a` or `entity_b` — recursive CTE performance degrades on large graphs.
