"""Where a research agent's stored findings live during a run.

`mp finding add` appends one JSON line per accepted finding. The agent
dispatcher reads the same file when the agent exits, so findings stored before
a turn cap or a crash still count.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOOKKEEPING = ("agent", "stored_at")


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
