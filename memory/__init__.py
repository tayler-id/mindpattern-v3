"""Memory module for mindpattern v3.

Public API for the research agent's institutional memory. All functions operate
on a sqlite3.Connection — no subprocess calls, no CLI, no cold starts.

The embedding model (BAAI/bge-small-en-v1.5) loads ONCE when this module is
first imported and stays resident for the lifetime of the process.

Usage:
    from memory import open_db, store_finding, search_findings

    with open_db() as db:
        fid = store_finding(db, "2026-03-14", "news-researcher", "Title", "Summary")
        results = search_findings(db, "multi-agent systems", limit=5)
"""

# Database
from .db import get_db, open_db

# Embeddings
from .embeddings import embed_text, embed_texts, cosine_similarity

# Findings & research
from .findings import (
    store_finding,
    search_findings,
    get_context,
    store_source,
    get_top_sources,
    store_skill,
    search_skills,
    list_skills,
    evaluate_run,
    log_agent_run,
    get_stats,
    backfill_from_reports,
)

# Feedback & preferences
from .feedback import (
    fetch_feedback,
    list_feedback,
    get_feedback_context,
    search_feedback,
    get_feedback_footer,
    mark_processed,
    set_preference,
    get_preference,
    accumulate_preference,
    list_preferences,
    get_preference_context,
    apply_preference_decay,
)

# Social pipeline
from .social import (
    store_post,
    recent_posts,
    check_duplicate,
    get_exemplars,
    store_social_feedback,
    get_feedback_patterns,
    store_engagement,
    check_engagement,
    list_engagements,
    store_pending_post,
    get_pending_posts,
    mark_pending_posted,
    count_posts_today,
)

# Agent evolution
from .evolution import (
    get_candidates,
    check_agent_performance,
    compute_overlap,
    log_evolution,
    spawn_agent,
    retire_agent,
    merge_agents,
)

# Patterns & self-improvement
from .patterns import (
    record_pattern,
    get_recurring,
    consolidate,
    promote,
    prune,
    store_note,
    get_recent_notes,
    backfill_note_embeddings,
)

# Signals
from .signals import (
    store_signal,
    get_signal_context,
    get_recent_signals,
)

# Cross-agent topic claiming (NEW in v3)
from .claims import (
    claim_topic,
    is_claimed,
    list_claims,
    clear_claims,
)

# Failure lessons (NEW in v3)
from .failures import (
    store_failure,
    recent_failures,
    failures_for_date,
    failure_categories,
)

# Editorial corrections (NEW in v3)
from .corrections import (
    store_correction,
    recent_corrections,
    correction_stats,
)

# Obsidian vault I/O (NEW in v3.1)
from .vault import (
    atomic_write,
    read_source_file,
    update_section,
    append_entry,
    get_recent_entries,
    archive_old_entries,
)

# Obsidian mirror generation (NEW in v3.1)
from .mirror import generate_mirrors

# Identity evolution (NEW in v3.1)
from .identity_evolve import (
    build_evolve_prompt,
    apply_evolution_diff,
    parse_llm_output,
)

# Entity graph (NEW in v3)
from .graph import (
    store_relationship,
    query_entity,
    find_path,
    related_entities,
    entity_stats,
)

__all__ = [
    # Database
    "get_db", "open_db",
    # Embeddings
    "embed_text", "embed_texts", "cosine_similarity",
    # Findings
    "store_finding", "search_findings", "get_context",
    "store_source", "get_top_sources",
    "store_skill", "search_skills", "list_skills",
    "evaluate_run", "log_agent_run", "get_stats",
    "backfill_from_reports",
    # Feedback
    "fetch_feedback", "list_feedback", "get_feedback_context",
    "search_feedback", "get_feedback_footer", "mark_processed",
    "set_preference", "get_preference", "accumulate_preference",
    "list_preferences", "get_preference_context", "apply_preference_decay",
    # Social
    "store_post", "recent_posts", "check_duplicate", "get_exemplars",
    "store_social_feedback", "get_feedback_patterns",
    "store_engagement", "check_engagement", "list_engagements",
    "store_pending_post", "get_pending_posts", "mark_pending_posted",
    "count_posts_today",
    # Evolution
    "get_candidates", "check_agent_performance", "compute_overlap",
    "log_evolution", "spawn_agent", "retire_agent", "merge_agents",
    # Patterns
    "record_pattern", "get_recurring", "consolidate", "promote", "prune",
    "store_note", "get_recent_notes", "backfill_note_embeddings",
    # Signals
    "store_signal", "get_signal_context", "get_recent_signals",
    # Claims
    "claim_topic", "is_claimed", "list_claims", "clear_claims",
    # Failures
    "store_failure", "recent_failures", "failures_for_date", "failure_categories",
    # Corrections
    "store_correction", "recent_corrections", "correction_stats",
    # Graph
    "store_relationship", "query_entity", "find_path",
    "related_entities", "entity_stats",
    # Vault
    "atomic_write", "read_source_file", "update_section",
    "append_entry", "get_recent_entries", "archive_old_entries",
    # Mirror
    "generate_mirrors",
    # Identity evolution
    "build_evolve_prompt", "apply_evolution_diff", "parse_llm_output",
]
