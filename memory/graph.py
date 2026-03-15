"""Entity extraction and graph queries using SQLite recursive CTEs.

Stores entity relationships in a flat table and uses recursive common table
expressions for path-finding and neighborhood queries. No external graph DB
required — everything runs in SQLite.
"""

import sqlite3
from datetime import datetime


def store_relationship(
    db: sqlite3.Connection,
    entity_a: str,
    relationship: str,
    entity_b: str,
    entity_a_type: str | None = None,
    entity_b_type: str | None = None,
    finding_id: int | None = None,
) -> int:
    """Store an entity relationship.

    Args:
        db: Database connection.
        entity_a: First entity name.
        relationship: Relationship label (e.g. 'works_at', 'competes_with').
        entity_b: Second entity name.
        entity_a_type: Optional type for entity_a (e.g. 'person', 'company').
        entity_b_type: Optional type for entity_b.
        finding_id: Optional FK to the findings table.

    Returns:
        Row ID of the inserted relationship.
    """
    cur = db.execute(
        """INSERT INTO entity_graph
               (entity_a, entity_a_type, relationship, entity_b, entity_b_type, finding_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            entity_a,
            entity_a_type,
            relationship,
            entity_b,
            entity_b_type,
            finding_id,
            datetime.now().isoformat(),
        ),
    )
    db.commit()
    return cur.lastrowid


def query_entity(db: sqlite3.Connection, name: str) -> dict:
    """Get all relationships for an entity (in either direction).

    Args:
        db: Database connection.
        name: Entity name to query.

    Returns:
        Dict with:
            - entity: the queried name
            - relationships: list of {related_entity, relationship, type, finding_id}
            - findings_count: number of unique findings linked to this entity
    """
    rows = db.execute(
        """SELECT entity_b AS related_entity, relationship, entity_b_type AS type, finding_id
           FROM entity_graph WHERE entity_a = ?
           UNION ALL
           SELECT entity_a AS related_entity, relationship, entity_a_type AS type, finding_id
           FROM entity_graph WHERE entity_b = ?""",
        (name, name),
    ).fetchall()

    relationships = [
        {
            "related_entity": r["related_entity"],
            "relationship": r["relationship"],
            "type": r["type"],
            "finding_id": r["finding_id"],
        }
        for r in rows
    ]

    finding_ids = {r["finding_id"] for r in relationships if r["finding_id"] is not None}

    return {
        "entity": name,
        "relationships": relationships,
        "findings_count": len(finding_ids),
    }


def find_path(
    db: sqlite3.Connection,
    entity_a: str,
    entity_b: str,
    max_depth: int = 4,
) -> list[dict] | None:
    """Find the shortest path between two entities using a recursive CTE.

    The graph is treated as undirected — edges are traversed in both directions.

    Args:
        db: Database connection.
        entity_a: Starting entity.
        entity_b: Target entity.
        max_depth: Maximum hops to search (default 4).

    Returns:
        List of {entity, relationship} dicts representing the path,
        or None if no path exists within max_depth.
    """
    rows = db.execute(
        """
        WITH RECURSIVE path_search(node, relationship, depth, visited) AS (
            -- Seed: start from entity_a
            SELECT ?, NULL, 0, ?

            UNION ALL

            -- Forward edges
            SELECT g.entity_b, g.relationship, p.depth + 1,
                   p.visited || '|' || g.entity_b
            FROM path_search p
            JOIN entity_graph g ON g.entity_a = p.node
            WHERE p.depth < ?
              AND INSTR(p.visited, '|' || g.entity_b) = 0

            UNION ALL

            -- Reverse edges
            SELECT g.entity_a, g.relationship, p.depth + 1,
                   p.visited || '|' || g.entity_a
            FROM path_search p
            JOIN entity_graph g ON g.entity_b = p.node
            WHERE p.depth < ?
              AND INSTR(p.visited, '|' || g.entity_a) = 0
        )
        SELECT node, relationship, depth, visited
        FROM path_search
        WHERE node = ?
        ORDER BY depth ASC
        LIMIT 1
        """,
        (entity_a, entity_a, max_depth, max_depth, entity_b),
    ).fetchall()

    if not rows:
        return None

    row = rows[0]
    visited_str = row["visited"]
    # visited is "A|B|C|D" — the full path of entity names
    path_nodes = visited_str.split("|")

    # Reconstruct path with relationships by walking edges
    path = [{"entity": path_nodes[0], "relationship": None}]
    for i in range(1, len(path_nodes)):
        prev = path_nodes[i - 1]
        curr = path_nodes[i]
        rel_row = db.execute(
            """SELECT relationship FROM entity_graph
               WHERE (entity_a = ? AND entity_b = ?)
                  OR (entity_a = ? AND entity_b = ?)
               LIMIT 1""",
            (prev, curr, curr, prev),
        ).fetchone()
        rel = rel_row["relationship"] if rel_row else None
        path.append({"entity": curr, "relationship": rel})

    return path


def related_entities(
    db: sqlite3.Connection,
    name: str,
    depth: int = 1,
) -> list[dict]:
    """Get entities within N hops of a given entity.

    Args:
        db: Database connection.
        name: Starting entity name.
        depth: Maximum hops (default 1 = direct neighbors).

    Returns:
        List of {entity, type, depth} dicts, sorted by depth then name.
    """
    rows = db.execute(
        """
        WITH RECURSIVE neighbors(node, node_type, hop, visited) AS (
            SELECT ?, NULL, 0, ?

            UNION ALL

            SELECT g.entity_b, g.entity_b_type, n.hop + 1,
                   n.visited || '|' || g.entity_b
            FROM neighbors n
            JOIN entity_graph g ON g.entity_a = n.node
            WHERE n.hop < ?
              AND INSTR(n.visited, '|' || g.entity_b) = 0

            UNION ALL

            SELECT g.entity_a, g.entity_a_type, n.hop + 1,
                   n.visited || '|' || g.entity_a
            FROM neighbors n
            JOIN entity_graph g ON g.entity_b = n.node
            WHERE n.hop < ?
              AND INSTR(n.visited, '|' || g.entity_a) = 0
        )
        SELECT DISTINCT node AS entity, node_type AS type, MIN(hop) AS depth
        FROM neighbors
        WHERE node != ?
        GROUP BY node
        ORDER BY depth, node
        """,
        (name, name, depth, depth, name),
    ).fetchall()

    return [
        {"entity": r["entity"], "type": r["type"], "depth": r["depth"]}
        for r in rows
    ]


def entity_stats(db: sqlite3.Connection) -> dict:
    """Stats on the entity graph.

    Args:
        db: Database connection.

    Returns:
        Dict with:
            - total_entities: unique entity count
            - total_relationships: row count in entity_graph
            - top_entities: list of {entity, connection_count} (top 20)
    """
    total_rels_row = db.execute(
        "SELECT COUNT(*) as cnt FROM entity_graph"
    ).fetchone()
    total_relationships = total_rels_row["cnt"]

    # Unique entities appear as entity_a or entity_b
    entity_count_row = db.execute(
        """SELECT COUNT(DISTINCT entity) as cnt FROM (
               SELECT entity_a AS entity FROM entity_graph
               UNION
               SELECT entity_b AS entity FROM entity_graph
           )"""
    ).fetchone()
    total_entities = entity_count_row["cnt"]

    # Top entities by connection count
    top_rows = db.execute(
        """SELECT entity, SUM(cnt) as connection_count FROM (
               SELECT entity_a AS entity, COUNT(*) as cnt FROM entity_graph GROUP BY entity_a
               UNION ALL
               SELECT entity_b AS entity, COUNT(*) as cnt FROM entity_graph GROUP BY entity_b
           )
           GROUP BY entity
           ORDER BY connection_count DESC
           LIMIT 20"""
    ).fetchall()
    top_entities = [
        {"entity": r["entity"], "connection_count": r["connection_count"]}
        for r in top_rows
    ]

    return {
        "total_entities": total_entities,
        "total_relationships": total_relationships,
        "top_entities": top_entities,
    }
