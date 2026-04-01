"""Database connection management and schema initialization.

Manages SQLite connections with WAL mode, foreign keys, and context managers.
Initializes all tables (17 existing + new v3 tables) with proper constraints.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_DIR = Path(__file__).parent.parent / "data"


def get_db(db_path: str | Path | None = None, user_id: str = "ramsay") -> sqlite3.Connection:
    """Open (and optionally initialize) the memory database.

    Args:
        db_path: Explicit path to the database file.
        user_id: User ID for default path resolution (data/{user_id}/memory.db).

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row.
    """
    if db_path:
        path = Path(db_path)
    else:
        path = DEFAULT_DB_DIR / user_id / "memory.db"

    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    _init_schema(conn)
    return conn


@contextmanager
def open_db(db_path: str | Path | None = None, user_id: str = "ramsay"):
    """Context manager for database connections. Auto-closes on exit."""
    conn = get_db(db_path, user_id)
    try:
        yield conn
    finally:
        conn.close()


def _init_schema(conn: sqlite3.Connection):
    """Initialize all tables with IF NOT EXISTS. Safe to call repeatedly.

    Fixes from v2:
    - FOREIGN KEY constraints on all embedding tables
    - DEFAULT (datetime('now')) on all created_at columns
    - Compound index on findings(run_date, agent)
    - Consistent TEXT type for all datetime columns
    - FTS5 virtual table for keyword search
    """
    conn.executescript("""
        -- ── Core research tables ──────────────────────────────────────

        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            agent TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            importance TEXT DEFAULT 'medium',
            category TEXT,
            source_url TEXT,
            source_name TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS findings_embeddings (
            finding_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            FOREIGN KEY (finding_id) REFERENCES findings(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_domain TEXT NOT NULL UNIQUE,
            display_name TEXT,
            hit_count INTEGER DEFAULT 0,
            high_value_count INTEGER DEFAULT 0,
            last_seen TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            theme TEXT NOT NULL,
            description TEXT,
            recurrence_count INTEGER DEFAULT 1,
            first_seen TEXT,
            last_seen TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS patterns_embeddings (
            pattern_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            FOREIGN KEY (pattern_id) REFERENCES patterns(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            domain TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            steps TEXT,
            difficulty TEXT DEFAULT 'intermediate',
            source_url TEXT,
            source_name TEXT,
            backfilled INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS skills_embeddings (
            skill_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
        );

        -- ── Feedback & preferences ────────────────────────────────────

        CREATE TABLE IF NOT EXISTS user_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT UNIQUE,
            from_email TEXT NOT NULL,
            subject TEXT,
            body TEXT NOT NULL,
            received_at TEXT NOT NULL,
            processed INTEGER DEFAULT 0,
            processed_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS feedback_embeddings (
            feedback_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            FOREIGN KEY (feedback_id) REFERENCES user_feedback(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            topic TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(email, topic)
        );

        -- ── Social pipeline ───────────────────────────────────────────

        CREATE TABLE IF NOT EXISTS social_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            platform TEXT NOT NULL,
            content TEXT NOT NULL,
            post_type TEXT DEFAULT 'single',
            anchor_text TEXT,
            brief_json TEXT,
            gate2_action TEXT,
            iterations INTEGER DEFAULT 1,
            posted INTEGER DEFAULT 0,
            platform_post_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS social_posts_embeddings (
            post_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            FOREIGN KEY (post_id) REFERENCES social_posts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS social_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            platform TEXT NOT NULL,
            action TEXT NOT NULL,
            original_draft TEXT,
            final_draft TEXT,
            user_feedback TEXT,
            edit_type TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS engagements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            engagement_type TEXT NOT NULL,
            target_post_url TEXT,
            target_author TEXT,
            target_author_id TEXT,
            target_content TEXT,
            our_reply TEXT,
            status TEXT DEFAULT 'drafted',
            finding_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            posted_at TEXT
        );

        -- ── Pending posts (deferred posting window) ────────────────────

        CREATE TABLE IF NOT EXISTS pending_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            content TEXT NOT NULL,
            image_path TEXT,
            approved_at TEXT NOT NULL,
            post_after TEXT NOT NULL,
            posted INTEGER DEFAULT 0,
            posted_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- ── Agent self-improvement ────────────────────────────────────

        CREATE TABLE IF NOT EXISTS agent_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            agent TEXT NOT NULL,
            note_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_notes_embeddings (
            note_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            FOREIGN KEY (note_id) REFERENCES agent_notes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS validated_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_key TEXT UNIQUE NOT NULL,
            distilled_rule TEXT NOT NULL,
            source_agents TEXT NOT NULL,
            observation_count INTEGER DEFAULT 1,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            promoted_to TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS validated_patterns_embeddings (
            pattern_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            FOREIGN KEY (pattern_id) REFERENCES validated_patterns(id) ON DELETE CASCADE
        );

        -- ── Cross-pipeline signals ────────────────────────────────────

        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pipeline TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            topic TEXT NOT NULL,
            strength REAL NOT NULL,
            evidence TEXT,
            run_date TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- ── Run tracking ──────────────────────────────────────────────

        CREATE TABLE IF NOT EXISTS run_quality (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT UNIQUE NOT NULL,
            total_findings INTEGER DEFAULT 0,
            unique_sources INTEGER DEFAULT 0,
            high_value_count INTEGER DEFAULT 0,
            trending_coverage REAL DEFAULT 0.0,
            dedup_rate REAL DEFAULT 0.0,
            agent_utilization REAL DEFAULT 0.0,
            source_diversity REAL DEFAULT 0.0,
            overall_score REAL DEFAULT 0.0,
            details_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS approval_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            decided_at TEXT,
            token TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approval_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER NOT NULL,
            platform TEXT,
            content_type TEXT,
            content TEXT,
            image_url TEXT,
            status TEXT DEFAULT 'pending',
            feedback TEXT,
            FOREIGN KEY (review_id) REFERENCES approval_reviews(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            run_date TEXT NOT NULL,
            findings_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- ── NEW v3 tables ─────────────────────────────────────────────

        CREATE TABLE IF NOT EXISTS claimed_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            agent TEXT NOT NULL,
            topic_hash TEXT NOT NULL,
            url TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(run_date, topic_hash)
        );

        CREATE TABLE IF NOT EXISTS failure_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            category TEXT NOT NULL,
            what_went_wrong TEXT NOT NULL,
            lesson TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS editorial_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            original_text TEXT NOT NULL,
            approved_text TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS entity_graph (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_a TEXT NOT NULL,
            entity_a_type TEXT,
            relationship TEXT NOT NULL,
            entity_b TEXT NOT NULL,
            entity_b_type TEXT,
            finding_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (finding_id) REFERENCES findings(id) ON DELETE SET NULL
        );

        -- ── Indexes ───────────────────────────────────────────────────

        CREATE INDEX IF NOT EXISTS idx_findings_date ON findings(run_date);
        CREATE INDEX IF NOT EXISTS idx_findings_agent ON findings(agent);
        CREATE INDEX IF NOT EXISTS idx_findings_importance ON findings(importance);
        CREATE INDEX IF NOT EXISTS idx_findings_date_agent ON findings(run_date, agent);
        CREATE INDEX IF NOT EXISTS idx_patterns_theme ON patterns(theme);
        CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(url_domain);
        CREATE INDEX IF NOT EXISTS idx_skills_domain ON skills(domain);
        CREATE INDEX IF NOT EXISTS idx_skills_date ON skills(run_date);
        CREATE INDEX IF NOT EXISTS idx_feedback_processed ON user_feedback(processed);
        CREATE INDEX IF NOT EXISTS idx_feedback_from ON user_feedback(from_email);
        CREATE INDEX IF NOT EXISTS idx_preferences_email ON user_preferences(email);
        CREATE INDEX IF NOT EXISTS idx_social_posts_date ON social_posts(date);
        CREATE INDEX IF NOT EXISTS idx_social_posts_platform ON social_posts(platform);
        CREATE INDEX IF NOT EXISTS idx_social_feedback_date ON social_feedback(date);
        CREATE INDEX IF NOT EXISTS idx_social_feedback_platform ON social_feedback(platform);
        CREATE INDEX IF NOT EXISTS idx_engagements_user ON engagements(user_id);
        CREATE INDEX IF NOT EXISTS idx_engagements_platform ON engagements(platform);
        CREATE INDEX IF NOT EXISTS idx_engagements_author ON engagements(target_author_id, platform);
        CREATE INDEX IF NOT EXISTS idx_engagements_created ON engagements(created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_notes_agent ON agent_notes(agent);
        CREATE INDEX IF NOT EXISTS idx_agent_notes_date ON agent_notes(run_date);
        CREATE INDEX IF NOT EXISTS idx_agent_notes_type ON agent_notes(note_type);
        CREATE INDEX IF NOT EXISTS idx_vp_status ON validated_patterns(status);
        CREATE INDEX IF NOT EXISTS idx_vp_key ON validated_patterns(pattern_key);
        CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(run_date);
        CREATE INDEX IF NOT EXISTS idx_signals_pipeline ON signals(source_pipeline);
        CREATE INDEX IF NOT EXISTS idx_rq_date ON run_quality(run_date);
        CREATE INDEX IF NOT EXISTS idx_approval_reviews_token ON approval_reviews(token);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_run_log_agent_date ON run_log(agent, run_date);

        -- v3 indexes
        CREATE INDEX IF NOT EXISTS idx_claimed_topics_date ON claimed_topics(run_date);
        CREATE INDEX IF NOT EXISTS idx_claimed_topics_hash ON claimed_topics(topic_hash);
        CREATE INDEX IF NOT EXISTS idx_failure_lessons_date ON failure_lessons(run_date);
        CREATE INDEX IF NOT EXISTS idx_failure_lessons_category ON failure_lessons(category);
        CREATE INDEX IF NOT EXISTS idx_editorial_corrections_platform ON editorial_corrections(platform);
        CREATE INDEX IF NOT EXISTS idx_entity_graph_a ON entity_graph(entity_a);
        CREATE INDEX IF NOT EXISTS idx_entity_graph_b ON entity_graph(entity_b);
        CREATE INDEX IF NOT EXISTS idx_entity_graph_finding ON entity_graph(finding_id);
    """)

    # FTS5 virtual table for keyword search (separate because CREATE VIRTUAL TABLE
    # doesn't support IF NOT EXISTS in all SQLite versions the same way)
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS findings_fts USING fts5(
                title, summary, content='findings', content_rowid='id'
            )
        """)
    except sqlite3.OperationalError:
        pass  # FTS5 may not be available in all builds

    conn.commit()


def migrate_existing_db(conn: sqlite3.Connection):
    """Apply schema fixes to an existing v2 database.

    Safe to run multiple times — all operations are idempotent.
    Called automatically by _init_schema for new tables/indexes.
    This handles data-level fixes that CREATE IF NOT EXISTS doesn't cover.
    """
    # Fix engagements.created_at type inconsistency
    # (v2 used TIMESTAMP, v3 uses TEXT — SQLite doesn't enforce types so
    # existing data is fine, but we add the compound index)
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_findings_date_agent ON findings(run_date, agent)"
        )
    except sqlite3.OperationalError:
        pass

    conn.commit()
