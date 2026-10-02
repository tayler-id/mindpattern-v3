"""Output contracts: the JSON Schema files in contracts/ and a checker for them.

A contract names the shape a model must answer in. Codex enforces it at the
source (`--output-schema`), and Python checks the parsed answer here for every
provider, because a schema the model was asked to follow is not a schema it
followed.

The checker covers the subset the contracts use: type, properties, required,
additionalProperties, enum, minimum, maximum, minLength, maxLength, items,
maxItems. No dependency: `jsonschema` is not in requirements.txt.
"""

from __future__ import annotations

import json
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
}


def path(name: str) -> Path:
    return CONTRACTS_DIR / f"{name}.schema.json"


def load(name: str) -> dict:
    return json.loads(path(name).read_text())


def errors(value: object, schema: dict, where: str = "$") -> list[str]:
    """Every way `value` breaks `schema`. Empty means it conforms."""
    expected = schema.get("type")
    if expected:
        python_type = _TYPES[expected]
        is_bool = isinstance(value, bool)
        if not isinstance(value, python_type) or (is_bool and expected in ("number", "integer")):
            return [f"{where}: expected {expected}, got {type(value).__name__}"]
    found: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            found.append(f"{where}: {value} is below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            found.append(f"{where}: {value} is above {schema['maximum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            found.append(f"{where}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            found.append(f"{where}: longer than {schema['maxLength']} characters")
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            found.append(f"{where}: more than {schema['maxItems']} items")
        if "items" in schema:
            for index, item in enumerate(value):
                found.extend(errors(item, schema["items"], f"{where}[{index}]"))
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                found.append(f"{where}: missing {key!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    found.append(f"{where}: unexpected key {key!r}")
        for key, sub in properties.items():
            if key in value:
                found.extend(errors(value[key], sub, f"{where}.{key}"))
    return found


def check(name: str, value: object) -> list[str]:
    return errors(value, load(name))
