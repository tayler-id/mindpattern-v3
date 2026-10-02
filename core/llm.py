"""Pull a JSON value out of model output.

Model calls go through core.model_cli. This module keeps the one helper the
callers share: JSON salvage from bare, fenced, or embedded output.
"""

import json


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
