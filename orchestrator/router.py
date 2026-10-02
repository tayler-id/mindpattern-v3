"""Model routing: which model, turn limit, and timeout each task gets.

The answers live in config/models.json, loaded and validated by core.config.
These helpers keep the call sites that ask the router by task name working.
"""

from core.config import Route, route_for

# The CLI's own turn limit applies when a route sets none; callers that log a
# number get the old router default.
DEFAULT_MAX_TURNS = 10


def get_route(task_type: str) -> Route:
    return route_for(task_type)


def get_model(task_type: str) -> str:
    """The model ID for a task type."""
    return route_for(task_type).model


def get_max_turns(task_type: str) -> int:
    """The turn limit for a task type."""
    return route_for(task_type).max_turns or DEFAULT_MAX_TURNS


def get_timeout(task_type: str) -> int:
    """The timeout in seconds for a task type."""
    return route_for(task_type).timeout_s
