"""Small JSON/text helpers on top of the Claude CLI process boundary.

The subprocess behavior lives in core.claude_cli. This module keeps the
existing text and JSON convenience contracts:

run()  -> raw text or None          (text helper)
ask()  -> schema-valid dict or None (JSON helper)
"""

import json
import logging

from .claude_cli import run_claude_process

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_TIMEOUT = 300


def run(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    allowed_tools: list[str] | None = None,
) -> str | None:
    """One claude -p call. Returns stdout text, or None on failure/timeout."""
    cmd = ["claude", "-p", prompt, "--model", model]
    if allowed_tools is not None:
        cmd += ["--allowedTools", ",".join(allowed_tools)]

    result = run_claude_process(cmd, timeout=timeout)
    if result.timed_out:
        return None

    if result.returncode != 0:
        logger.warning("claude exited %d: %s", result.returncode, (result.stderr or "")[:200])
        return None
    return result.stdout


def ask(
    prompt: str,
    schema: dict,
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    allowed_tools: list[str] | None = None,
) -> dict | None:
    """claude call that must return JSON matching `schema`.

    Schema is a minimal subset: {"required": [...], "properties": {name:
    {"type": "string"|"number"|"boolean"|"array"|"object"}}}. One retry with
    error feedback, then None — callers skip the item, never crash.
    """
    attempt_prompt = prompt
    for attempt in range(2):
        out = run(attempt_prompt, model=model, timeout=timeout, allowed_tools=allowed_tools)
        if out is None:
            return None
        data = extract_json(out)
        error = _validate(data, schema)
        if error is None:
            return data
        logger.info("llm output invalid (attempt %d): %s", attempt + 1, error)
        attempt_prompt = (
            f"{prompt}\n\nYour previous reply was invalid: {error}.\n"
            f"Reply with ONLY a JSON object matching the requirements — no prose."
        )
    logger.warning("llm output invalid after retry: %s", prompt[:80])
    return None


def extract_json(text: str):
    """Pull a JSON object/array out of model output (bare, fenced, or embedded)."""
    text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    if "```" in text:
        for chunk in text.split("```")[1::2]:
            chunk = chunk.removeprefix("json").strip()
            try:
                return json.loads(chunk)
            except (json.JSONDecodeError, ValueError):
                continue
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if 0 <= start < end:
            try:
                return json.loads(text[start : end + 1])
            except (json.JSONDecodeError, ValueError):
                continue
    return None


_TYPES = {
    "string": str,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _validate(data, schema: dict) -> str | None:
    """Return an error description, or None if data matches the schema."""
    if data is None:
        return "no JSON found in output"
    if not isinstance(data, dict):
        return f"expected a JSON object, got {type(data).__name__}"
    for key in schema.get("required", []):
        if key not in data:
            return f"missing required key '{key}'"
    for key, spec in schema.get("properties", {}).items():
        if key in data and data[key] is not None:
            expected = _TYPES.get(spec.get("type"))
            if expected and not isinstance(data[key], expected):
                return f"key '{key}' should be {spec['type']}"
            if expected is list and isinstance(data[key], bool):
                return f"key '{key}' should be array"
    return None
