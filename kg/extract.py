"""Typed entity/edge extraction from findings via the Claude CLI.

Same process boundary as the site writer (``claude -p`` under the existing
subscription — no new providers or credentials). Extraction is *constrained*:
closed entity-type and predicate vocabularies from ``kg.schema``, strict JSON
output, and deterministic validation that drops anything outside the
vocabulary instead of trusting the model. A batch that fails to parse fails
open (those findings are marked failed and can be retried); nothing raises
into the caller.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from core.llm import extract_json
from kg.schema import ENTITY_TYPES, FACT_TYPES, PREDICATES

logger = logging.getLogger(__name__)

KG_MODEL_ENV = "MP_KG_MODEL"
DEFAULT_KG_MODEL = "claude-haiku-4-5-20251001"

MAX_ENTITIES_PER_FINDING = 8
MAX_EDGES_PER_FINDING = 6
MAX_ENTITY_NAME_CHARS = 60
MAX_ENTITY_NAME_WORDS = 6

_PROMPT_HEADER = """You are an information-extraction system for an AI-industry knowledge graph.
For EACH finding below, extract named entities and typed relationships.

Entity types (closed vocabulary — use exactly these):
{entity_types}

Predicates (closed vocabulary — use exactly these):
{predicates}

Fact types: Fact (established/reported event), Opinion (someone's judgement),
Prediction (claim about the future). A PREDICTS edge is always fact_type Prediction.

Rules:
- Only extract entities literally named in the finding text. Never invent or infer names.
- Entity names are short proper nouns exactly as written (e.g. "Anthropic",
  "Claude Fable 5", "Sam Altman", "SWE-bench"). Never a sentence, headline,
  domain name, or description. Max {max_words} words and {max_chars} characters.
- Never output a name made only of generic words ("Update", "Launch",
  "Report", "News") — skip it instead.
- "Product" covers AI models. Papers use their short title.
- Every edge's subject and object MUST appear in that finding's entities list.
- An edge's subject and object must be different entities (no self-loops).
- Prefer the most specific predicate; use MENTIONS only when nothing else fits,
  and at most one MENTIONS edge per finding.
- fact_text is one short sentence stating the fact in plain words.
- confidence: 1.0 = stated outright, 0.7 = strongly implied, 0.5 = weakly implied.
- If a finding names no real entities, return it with empty lists.
- Output at most {max_entities} entities and {max_edges} edges per finding.

Return ONLY a JSON object, no markdown fences, exactly this shape:
{{"findings": [{{"id": <finding id>,
   "entities": [{{"name": "...", "type": "..."}}],
   "edges": [{{"subject": "...", "predicate": "...", "object": "...",
               "fact": "...", "fact_type": "...", "confidence": 0.9}}]}}]}}

Findings:
"""


def build_extraction_prompt(findings: list[dict[str, Any]]) -> str:
    """Render the batch prompt for a list of finding rows."""
    header = _PROMPT_HEADER.format(
        entity_types=", ".join(ENTITY_TYPES),
        predicates=", ".join(PREDICATES),
        max_words=MAX_ENTITY_NAME_WORDS,
        max_chars=MAX_ENTITY_NAME_CHARS,
        max_entities=MAX_ENTITIES_PER_FINDING,
        max_edges=MAX_EDGES_PER_FINDING,
    )
    payload = [
        {
            "id": int(f["id"]),
            "date": str(f.get("run_date") or ""),
            "title": str(f.get("title") or "")[:300],
            "summary": str(f.get("summary") or "")[:700],
        }
        for f in findings
    ]
    return header + json.dumps(payload, ensure_ascii=False, indent=1)


def extraction_command(prompt: str, *, model: str | None = None) -> list[str]:
    """argv for one extraction call. Read-only: every tool disallowed."""
    return [
        "claude",
        "-p",
        prompt,
        "--model",
        model or os.environ.get(KG_MODEL_ENV, DEFAULT_KG_MODEL),
        "--max-turns",
        "1",
        "--output-format",
        "text",
        "--disallowedTools",
        "Agent,Bash,Write,Edit,NotebookEdit,Skill,WebFetch,WebSearch,Read,Grep,Glob",
    ]


def parse_extraction_output(stdout: str) -> list[dict[str, Any]]:
    """Parse model output into per-finding extraction dicts. [] on any failure.

    JSON salvage is delegated to ``core.llm.extract_json`` (bare, fenced, or
    embedded payloads — strictly more shapes than the fence regex this
    replaced); only the ``findings`` unwrap is KG-specific.
    """
    text = (stdout or "").strip()
    if not text:
        return []
    data = extract_json(text)
    if data is None:
        logger.warning("kg extraction: unparseable model output (%d chars)", len(stdout or ""))
        return []
    items = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _clean_name(value: Any) -> str:
    name = re.sub(r"\s+", " ", str(value or "")).strip().strip("\"'`“”‘’")
    return name.rstrip(".,;:!?")


def validate_extraction(
    item: dict[str, Any], *, allowed_ids: set[int]
) -> dict[str, Any] | None:
    """Deterministically enforce the closed vocabularies on one finding's output.

    Returns {"id", "entities", "edges"} with only valid rows, or None when the
    item is malformed or refers to a finding outside this batch. Never raises
    on malformed shapes (non-dict items, non-list entities/edges) — the
    fail-open contract of both callers depends on that.
    """
    if not isinstance(item, dict):
        return None
    try:
        finding_id = int(item.get("id"))
    except (TypeError, ValueError):
        return None
    if finding_id not in allowed_ids:
        return None

    raw_entities = item.get("entities")
    if not isinstance(raw_entities, list):
        raw_entities = []
    raw_edges = item.get("edges")
    if not isinstance(raw_edges, list):
        raw_edges = []

    # casefolded key -> (display name, entity type)
    entities: dict[str, tuple[str, str]] = {}
    for raw in raw_entities[:MAX_ENTITIES_PER_FINDING]:
        if not isinstance(raw, dict):
            continue
        name = _clean_name(raw.get("name"))
        etype = str(raw.get("type") or "").strip()
        if not name or etype not in ENTITY_TYPES:
            continue
        if len(name) > MAX_ENTITY_NAME_CHARS or len(name.split()) > MAX_ENTITY_NAME_WORDS:
            continue
        entities.setdefault(name.casefold(), (name, etype))

    names = {key: name for key, (name, _etype) in entities.items()}
    valid_entities = [
        {"name": name, "type": etype} for name, etype in entities.values()
    ]

    edges: list[dict[str, Any]] = []
    mentions_used = 0
    for raw in raw_edges[:MAX_EDGES_PER_FINDING * 2]:
        if len(edges) >= MAX_EDGES_PER_FINDING or not isinstance(raw, dict):
            continue
        subject = _clean_name(raw.get("subject"))
        obj = _clean_name(raw.get("object"))
        predicate = str(raw.get("predicate") or "").strip().upper()
        fact_type = str(raw.get("fact_type") or "Fact").strip().title()
        fact = re.sub(r"\s+", " ", str(raw.get("fact") or "")).strip()[:300]
        if predicate not in PREDICATES or fact_type not in FACT_TYPES:
            continue
        if subject.casefold() not in names or obj.casefold() not in names:
            continue
        if subject.casefold() == obj.casefold():
            continue
        if predicate == "PREDICTS":
            fact_type = "Prediction"
        if predicate == "MENTIONS":
            mentions_used += 1
            if mentions_used > 1:
                continue
        try:
            confidence = min(1.0, max(0.0, float(raw.get("confidence", 0.7))))
        except (TypeError, ValueError):
            confidence = 0.7
        if not fact:
            fact = f"{subject} {predicate.lower().replace('_', ' ')} {obj}"
        edges.append(
            {
                "subject": names[subject.casefold()],
                "predicate": predicate,
                "object": names[obj.casefold()],
                "fact_text": fact,
                "fact_type": fact_type,
                "confidence": confidence,
            }
        )

    return {"id": finding_id, "entities": valid_entities, "edges": edges}
