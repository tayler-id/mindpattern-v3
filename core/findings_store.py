"""Where a research agent's stored findings live during a run.

`mp finding add` appends one JSON line per accepted finding. The agent
dispatcher reads the same file when the agent exits, so findings stored before
a turn cap or a crash still count.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOOKKEEPING = ("agent", "stored_at")
CORROBORATIONS = "corroborations.jsonl"
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an and are as at be by for from has have in is it its of on or that the this to was were will with".split())


def normalize_url(url: str) -> str:
    url = (url or "").strip().lower()
    url = re.sub(r"^https?://(www\.)?", "", url)
    return url.split("#", 1)[0].rstrip("/")


def title_words(title: str) -> set[str]:
    """Content words of a title. Digits always count: Runtime 1.0 and 2.0 are different stories."""
    return {w for w in _WORD.findall((title or "").lower()) if w not in _STOP and (len(w) > 1 or w.isdigit())}


def title_overlap(a: str, b: str) -> float:
    left, right = title_words(a), title_words(b)
    return len(left & right) / len(left | right) if left and right else 0.0


def record_corroboration(store: Path, row: dict) -> None:
    """One agent found a story another agent already stored this run.

    Kept, not discarded: several agents finding a story is the selector's
    convergence signal, and until 2026-10-10 the selector never saw it.
    """
    append(store.parent / CORROBORATIONS, row)


def read_corroborations(run_dir: Path) -> list[dict]:
    return read_rows(run_dir / CORROBORATIONS)


def corroborators(finding: dict, rows: list[dict]) -> list[str]:
    """'agent (source)' for every other agent that found this finding's story."""
    url = normalize_url(finding.get("source_url", ""))
    found = []
    for row in rows:
        same = (url and normalize_url(row.get("corroborates_url", "")) == url) or \
            title_overlap(finding.get("title", ""), row.get("corroborates_title", "")) >= 0.6
        if same and row.get("agent") != finding.get("agent"):
            label = f"{row.get('agent')} ({row.get('source_name') or 'no source'})"
            if label not in found:
                found.append(label)
    return found


def path_for(user_id: str, run_id: str, agent: str) -> Path:
    return PROJECT_ROOT / "data" / user_id / "runs" / run_id / f"{agent}.findings.jsonl"


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def read_findings(path: Path) -> list[dict]:
    """Stored findings without the bookkeeping fields `mp` adds."""
    return [{k: v for k, v in row.items() if k not in BOOKKEEPING} for row in read_rows(path)]


def append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
