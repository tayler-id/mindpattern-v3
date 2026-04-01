"""Prompt compression via LLMLingua-2 for research agent dispatch.

Compresses static prompt sections (identity files, schema boilerplate, novelty
requirements) to reduce token count by 30-40% across 13 concurrent agent calls.
Dynamic sections (trends, claims, preflight items) pass through uncompressed.

Ticket: 2026-03-31-R005
"""

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Try to import LLMLingua — optional heavy dependency
try:
    from llmlingua import PromptCompressor

    LLMLINGUA_AVAILABLE = True
except ImportError:
    LLMLINGUA_AVAILABLE = False

_compressor = None


def _get_compressor():
    """Lazily initialize the LLMLingua-2 compressor."""
    global _compressor
    if _compressor is None and LLMLINGUA_AVAILABLE:
        _compressor = PromptCompressor(
            model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
            use_llmlingua2=True,
        )
    return _compressor


def compress_prompt(text: str, target_ratio: float = 0.5) -> str:
    """Compress a prompt using LLMLingua-2.

    Returns the original text if no compressor is available.
    """
    compressor = _get_compressor()
    if compressor is None:
        return text

    result = compressor.compress_prompt(
        [text],
        rate=target_ratio,
        force_tokens=["\n", "?", ".", "!", "{", "}", "[", "]", '"', ":"],
    )
    return result["compressed_prompt"]


def maybe_compress(text: str, config: dict) -> str:
    """Compress text only if prompt_compression_enabled is true in config."""
    if not config.get("prompt_compression_enabled", False):
        return text
    ratio = config.get("prompt_compression_ratio", 0.5)
    return compress_prompt(text, target_ratio=ratio)


# ---------------------------------------------------------------------------
# Compression cache (traces.db)
# ---------------------------------------------------------------------------


def init_compression_cache(conn: sqlite3.Connection) -> None:
    """Create the prompt_compression_cache table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prompt_compression_cache (
            content_hash TEXT PRIMARY KEY,
            original_tokens INTEGER,
            compressed_tokens INTEGER,
            compressed_text TEXT NOT NULL,
            target_ratio REAL NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL
        )
    """)
    conn.commit()


def compress_with_cache(
    conn: sqlite3.Connection,
    text: str,
    target_ratio: float = 0.5,
) -> str:
    """Compress text using cache. Returns cached version on hit, compresses on miss."""
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    # Check cache
    row = conn.execute(
        "SELECT compressed_text FROM prompt_compression_cache WHERE content_hash = ? AND target_ratio = ?",
        (content_hash, target_ratio),
    ).fetchone()

    if row is not None:
        # Cache hit — update stats
        conn.execute(
            "UPDATE prompt_compression_cache SET hit_count = hit_count + 1, last_used_at = ? "
            "WHERE content_hash = ? AND target_ratio = ?",
            (now, content_hash, target_ratio),
        )
        conn.commit()
        logger.info(f"Compression cache HIT: hash={content_hash[:12]}")
        return row["compressed_text"]

    # Cache miss — compress and store
    compressed = compress_prompt(text, target_ratio=target_ratio)
    original_tokens = len(text.split())
    compressed_tokens = len(compressed.split())

    conn.execute(
        "INSERT OR REPLACE INTO prompt_compression_cache "
        "(content_hash, original_tokens, compressed_tokens, compressed_text, "
        "target_ratio, hit_count, created_at, last_used_at) "
        "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
        (content_hash, original_tokens, compressed_tokens, compressed, target_ratio, now, now),
    )
    conn.commit()

    ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0
    logger.info(
        f"Compression cache MISS: hash={content_hash[:12]}, "
        f"{original_tokens} -> {compressed_tokens} tokens ({ratio:.1%})"
    )
    return compressed


# ---------------------------------------------------------------------------
# Quality gate
# ---------------------------------------------------------------------------


def check_quality_gate(
    baseline_counts: dict[str, int],
    compressed_counts: dict[str, int],
    threshold: float = 0.20,
) -> dict:
    """Check if any agent's finding count dropped >threshold after compression.

    Returns dict with should_disable bool and list of regressed agent names.
    """
    regressed = []
    for agent, baseline in baseline_counts.items():
        if baseline == 0:
            continue
        compressed = compressed_counts.get(agent, 0)
        drop = (baseline - compressed) / baseline
        if drop > threshold:
            regressed.append(agent)
            logger.warning(
                f"Quality gate: {agent} findings dropped {drop:.0%} "
                f"({baseline} -> {compressed}), threshold={threshold:.0%}"
            )

    should_disable = len(regressed) > 0
    if should_disable:
        logger.warning(
            f"Quality gate FAILED: {len(regressed)} agents regressed, "
            f"recommend disabling compression"
        )

    return {
        "should_disable": should_disable,
        "regressed_agents": regressed,
    }
