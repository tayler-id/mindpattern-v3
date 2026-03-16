"""Model routing — right model for each task.

Haiku for cheap scanning, Sonnet for agents, Opus for editorial judgment.
40-70% cost reduction compared to running everything on Opus.
"""

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
    "research_agent": "sonnet",     # good enough for search + extract
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
    "analyzer": "opus_1m",          # needs 1M context for all traces + skills
}

# Max turns per task type
MAX_TURNS: dict[str, int] = {
    "trend_scan": 5,
    "research_agent": 25,
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
    "analyzer": 10,
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
    "expeditor": 120,
    "humanizer": 120,
    "engagement_finder": 300,
    "engagement_writer": 120,
    "analyzer": 600,
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
