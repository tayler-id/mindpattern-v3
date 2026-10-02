"""Model routing config: one file decides which provider and model runs each task.

config/models.json maps a task name ("research_agent", "newsletter_writer", ...)
to a route. A task the file does not name uses its "_default" route. The file is
validated as a whole the first time it is read, so a typo fails the run before
any model call instead of halfway through it.

    .venv/bin/python3 -m core.config check
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_PATH = PROJECT_ROOT / "config" / "models.json"

PROVIDERS = ("claude", "codex")
EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")
DEFAULT_TASK = "_default"
_ROUTE_KEYS = {"provider", "model", "effort", "max_turns", "timeout_s", "fallback", "enabled"}


class ConfigError(ValueError):
    """A config file is missing, unreadable, or fails validation."""


@dataclass(frozen=True)
class Route:
    task: str
    provider: str
    model: str
    timeout_s: int
    effort: str | None = None
    max_turns: int | None = None
    fallback: Route | None = None
    enabled: bool = True


def _positive_int(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{where} must be a positive integer, got {value!r}")
    return value


def parse_route(task: str, raw: object, *, allow_fallback: bool = True) -> Route:
    where = f"config/models.json {task}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be an object")
    unknown = set(raw) - _ROUTE_KEYS
    if unknown:
        raise ConfigError(f"{where} has unknown keys: {', '.join(sorted(unknown))}")
    provider = raw.get("provider")
    if provider not in PROVIDERS:
        raise ConfigError(f"{where}.provider must be one of {PROVIDERS}, got {provider!r}")
    model = raw.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ConfigError(f"{where}.model must be a non-empty string")
    effort = raw.get("effort")
    if effort is not None and effort not in EFFORTS:
        raise ConfigError(f"{where}.effort must be one of {EFFORTS}, got {effort!r}")
    # Unset, a Claude call inherits the user's interactive effort (2026-10-02:
    # "high" from ~/.claude/settings.json). Haiku 4.5 rejects the flag.
    is_haiku = "haiku" in model.lower()
    if provider == "claude" and effort is None and not is_haiku:
        raise ConfigError(f"{where}.effort is required for a Claude model other than Haiku")
    if provider == "claude" and effort is not None and is_haiku:
        raise ConfigError(f"{where}.effort must be left out for Haiku, which takes no effort setting")
    max_turns = raw.get("max_turns")
    if max_turns is not None:
        max_turns = _positive_int(max_turns, f"{where}.max_turns")
    if "timeout_s" not in raw:
        raise ConfigError(f"{where}.timeout_s is required")
    timeout_s = _positive_int(raw["timeout_s"], f"{where}.timeout_s")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError(f"{where}.enabled must be true or false")
    fallback = None
    if raw.get("fallback") is not None:
        if not allow_fallback:
            raise ConfigError(f"{where}.fallback cannot itself have a fallback")
        fallback = parse_route(task, raw["fallback"], allow_fallback=False)
    return Route(task, provider, model, timeout_s, effort, max_turns, fallback, enabled)


def parse_routes(data: object) -> dict[str, Route]:
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), dict):
        raise ConfigError('config/models.json must be an object with a "tasks" object')
    routes = {task: parse_route(task, raw) for task, raw in data["tasks"].items()}
    if DEFAULT_TASK not in routes:
        raise ConfigError(f'config/models.json must define a "{DEFAULT_TASK}" task')
    return routes


_cache: dict[Path, tuple[float, dict[str, Route]]] = {}


def load_routes(path: Path = MODELS_PATH) -> dict[str, Route]:
    """Parsed routes, re-read only when the file changes."""
    try:
        mtime = path.stat().st_mtime
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    cached = _cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot parse {path}: {exc}") from exc
    routes = parse_routes(data)
    _cache[path] = (mtime, routes)
    return routes


def route_for(task: str, path: Path = MODELS_PATH) -> Route:
    routes = load_routes(path)
    route = routes.get(task)
    if route is None:
        default = routes[DEFAULT_TASK]
        return Route(task, default.provider, default.model, default.timeout_s,
                     default.effort, default.max_turns, default.fallback, default.enabled)
    return route


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] != ["check"]:
        print("usage: python -m core.config check [path-to-models.json]", file=sys.stderr)
        return 2
    path = Path(args[1]) if len(args) > 1 else MODELS_PATH
    try:
        routes = load_routes(path)
    except ConfigError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    for task, route in sorted(routes.items()):
        fallback = f" -> fallback {route.fallback.provider}:{route.fallback.model}" if route.fallback else ""
        state = "" if route.enabled else " (disabled)"
        print(f"{task:22} {route.provider:6} {route.model:22} effort={route.effort or '-':7} "
              f"turns={route.max_turns or '-':<3} timeout={route.timeout_s}s{fallback}{state}")
    print(f"OK: {len(routes)} routes in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
