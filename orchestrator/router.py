"""Model routing — right model for each task.

Haiku for cheap scanning, Sonnet for agents, Opus for editorial judgment.
40-70% cost reduction compared to running everything on Opus.

Adaptive routing: uses historical agent_metrics to assign models per agent.
Agents that consistently produce high-quality findings on Sonnet stay on Sonnet.
Agents that underperform get promoted to Opus.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Model IDs for claude CLI --model flag
MODELS = {
    "haiku": "haiku",
    "sonnet": "sonnet",
    "opus": "opus",
    "opus_1m": "claude-opus-4-6[1m]",
}

# Map each task type to its optimal model
MODEL_ROUTING: dict[str, str] = {
    # Research pipeline
    "trend_scan": "haiku",          # cheap, just URL scanning
    "research_agent": "opus_1m",      # deep research with full 1M context for papers, repos, long reads
    "synthesis_pass1": "opus_1m",    # editorial judgment + needs full findings in context
    "synthesis_pass2": "opus_1m",    # writing quality + full findings, 1M context
    "learnings_update": "sonnet",   # summarization

    # Social pipeline
    "eic": "opus_1m",               # editorial judgment + full findings context
    "creative_brief": "sonnet",     # writing
    "art_director": "sonnet",       # visual direction
    "illustrator": "sonnet",        # image prompt creation
    "writer": "sonnet",             # writing
    "critic": "sonnet",             # review
    "expeditor": "sonnet",          # quality check
    "humanizer": "sonnet",          # post-processing

    # Engagement
    "engagement_finder": "sonnet",  # search + match
    "engagement_writer": "sonnet",  # reply writing

    # Self-optimization
    "evolve": "opus_1m",            # needs 1M context for all traces + skills
    "identity": "sonnet",           # identity maintenance
}

# Max turns per task type
MAX_TURNS: dict[str, int] = {
    "trend_scan": 5,
    "research_agent": 35,
    "synthesis_pass1": 10,
    "synthesis_pass2": 30,
    "learnings_update": 5,
    "eic": 15,
    "creative_brief": 10,
    "art_director": 10,
    "illustrator": 5,
    "writer": 15,
    "critic": 5,
    "expeditor": 5,
    "humanizer": 5,
    "engagement_finder": 10,
    "engagement_writer": 5,
    "evolve": 10,
    "identity": 5,
}

# Timeout per task type (seconds)
TIMEOUTS: dict[str, int] = {
    "trend_scan": 60,
    "research_agent": 1800,     # 30 minutes per agent (Jina deep reads need time)
    "synthesis_pass1": 600,     # 10 minutes — Opus needs time for story selection
    "synthesis_pass2": 900,     # 15 minutes — Opus writing full newsletter
    "learnings_update": 120,
    "eic": 600,
    "creative_brief": 180,
    "art_director": 300,
    "illustrator": 180,
    "writer": 300,
    "critic": 120,
    "expeditor": 180,
    "humanizer": 120,
    "engagement_finder": 300,
    "engagement_writer": 120,
    "evolve": 600,
    "identity": 300,
}

# Cost per 1M tokens (for budget tracking)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "haiku": {"input": 0.25, "output": 1.25},
    "sonnet": {"input": 3.0, "output": 15.0},
    "opus": {"input": 15.0, "output": 75.0},
    "claude-opus-4-6[1m]": {"input": 15.0, "output": 75.0},
}


def get_model(task_type: str) -> str:
    """Get the model ID for a task type. Resolves aliases like opus_1m."""
    model_key = MODEL_ROUTING.get(task_type, "sonnet")
    return MODELS.get(model_key, model_key)


def get_max_turns(task_type: str) -> int:
    """Get max turns for a task type."""
    return MAX_TURNS.get(task_type, 10)


def get_timeout(task_type: str) -> int:
    """Get timeout in seconds for a task type."""
    return TIMEOUTS.get(task_type, 300)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a given model and token counts."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["sonnet"])
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 4)


# ---------------------------------------------------------------------------
# Adaptive routing — quality-driven cascade model selection
# ---------------------------------------------------------------------------

# Load adaptive routing flag from config.json
def _load_adaptive_routing_flag() -> bool:
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    try:
        with open(config_path) as f:
            return json.load(f).get("adaptive_routing_enabled", False)
    except (FileNotFoundError, json.JSONDecodeError):
        return False


ADAPTIVE_ROUTING_ENABLED: bool = _load_adaptive_routing_flag()

# Minimum number of recent runs required before adaptive routing kicks in
MIN_HISTORY_RUNS = 3

# Quality score threshold — agents scoring above this on Sonnet stay on Sonnet
QUALITY_THRESHOLD = 8.0

# Weights for composite quality score
QUALITY_WEIGHTS = {
    "findings_count": 0.7,
    "efficiency": 0.3,  # lower duration_ms per finding = better
}

# Expected findings per run (for normalizing the score)
EXPECTED_FINDINGS = 15


def compute_quality_score(findings_count: int, duration_ms: int) -> float:
    """Compute a composite quality score from agent metrics.

    Score components:
    - findings_count: normalized to 0-10 scale (EXPECTED_FINDINGS = 10.0)
    - efficiency: inverse of duration per finding, normalized to 0-10

    Returns a weighted score on a 0-10 scale.
    """
    # Findings component: 10 * (count / expected), capped at 10
    findings_score = min(10.0, 10.0 * findings_count / EXPECTED_FINDINGS)

    # Efficiency component: faster per-finding = better
    if findings_count > 0 and duration_ms > 0:
        ms_per_finding = duration_ms / findings_count
        # 2000ms per finding = 10, 60000ms per finding = ~0.3
        efficiency_score = min(10.0, 20000.0 / max(ms_per_finding, 1))
    else:
        efficiency_score = 0.0

    return (
        QUALITY_WEIGHTS["findings_count"] * findings_score
        + QUALITY_WEIGHTS["efficiency"] * efficiency_score
    )


def _log_routing_decision(
    conn: sqlite3.Connection,
    agent_name: str,
    assigned_model: str,
    quality_score: float | None,
    reason: str,
) -> None:
    """Log a routing decision to the model_routing_log table."""
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO model_routing_log (agent_name, run_date, assigned_model, quality_score, reason) "
        "VALUES (?, ?, ?, ?, ?)",
        (agent_name, run_date, assigned_model, quality_score, reason),
    )
    conn.commit()


def get_adaptive_model(
    conn: sqlite3.Connection,
    agent_name: str,
    task_type: str = "research_agent",
) -> str:
    """Get the model for an agent using adaptive quality-driven routing.

    Falls back to static routing when:
    - ADAPTIVE_ROUTING_ENABLED is False
    - Insufficient history (< MIN_HISTORY_RUNS runs)

    Cascade logic:
    - Query last 7 runs from agent_metrics
    - Compute average quality score
    - If recent runs were on Sonnet and quality >= threshold → keep Sonnet
    - If recent runs were on Sonnet and quality < threshold → promote to Opus
    - If insufficient history → default to Opus (static)
    """
    static_model = get_model(task_type)

    if not ADAPTIVE_ROUTING_ENABLED:
        _log_routing_decision(conn, agent_name, static_model, None, "Adaptive routing disabled, using static")
        return static_model

    # Query last 7 runs for this agent, ordered by date
    rows = conn.execute(
        """
        SELECT findings_count, duration_ms, model_used
        FROM agent_metrics
        WHERE agent_name = ?
        ORDER BY run_date DESC
        LIMIT 7
        """,
        (agent_name,),
    ).fetchall()

    if len(rows) < MIN_HISTORY_RUNS:
        _log_routing_decision(
            conn, agent_name, static_model, None,
            f"Insufficient history ({len(rows)} runs < {MIN_HISTORY_RUNS}), fallback to static",
        )
        return static_model

    # Compute average quality score across recent runs
    scores = [
        compute_quality_score(row["findings_count"], row["duration_ms"])
        for row in rows
    ]
    avg_score = sum(scores) / len(scores)

    # Check what model was used in recent runs
    recent_models = [row["model_used"] for row in rows[:MIN_HISTORY_RUNS]]
    all_on_sonnet = all(m == "sonnet" for m in recent_models)
    all_on_opus = all(
        m in ("opus", "opus_1m", "claude-opus-4-6[1m]") for m in recent_models
    )

    if all_on_sonnet and avg_score >= QUALITY_THRESHOLD:
        model = MODELS["sonnet"]
        reason = f"High quality on Sonnet (score={avg_score:.2f} >= {QUALITY_THRESHOLD}), keeping Sonnet"
        _log_routing_decision(conn, agent_name, model, avg_score, reason)
        return model

    if all_on_sonnet and avg_score < QUALITY_THRESHOLD:
        model = MODELS["opus_1m"]
        reason = f"Low quality on Sonnet (score={avg_score:.2f} < {QUALITY_THRESHOLD}), promoting to Opus"
        _log_routing_decision(conn, agent_name, model, avg_score, reason)
        return model

    if all_on_opus and avg_score >= QUALITY_THRESHOLD and len(rows) >= 5:
        # Trial demotion: consistently good on Opus for 5+ runs → try Sonnet
        model = MODELS["sonnet"]
        reason = f"High quality on Opus for 5+ runs (score={avg_score:.2f}), trial demotion to Sonnet"
        _log_routing_decision(conn, agent_name, model, avg_score, reason)
        return model

    # Mixed history or Opus without enough runs for demotion → keep static
    _log_routing_decision(
        conn, agent_name, static_model, avg_score,
        f"Mixed model history or insufficient Opus streak, using static (score={avg_score:.2f})",
    )
    return static_model
