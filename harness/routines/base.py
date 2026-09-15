"""Shared shapes for autonomous routines."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol


@dataclass
class Finding:
    """One mechanically-detected problem.

    ``repro`` is a shell command that must FAIL now and PASS once fixed —
    the contract `harness.gates.gate_repro_flips` enforces. A finding whose
    repro cannot be expressed that way is a report, not a fixable finding,
    and sets ``repro=""``.
    """

    routine: str
    kind: str
    title: str
    detail: str
    file: str = ""
    line: int = 0
    repro: str = ""
    truth_rows: list[dict] = field(default_factory=list)
    severity: str = "normal"  # "high" | "normal" | "low"

    def key(self) -> str:
        """Stable identity for dedup across nights."""
        return f"{self.routine}:{self.kind}:{self.file}:{self.line}:{self.title}"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RoutineResult:
    routine: str
    findings: list[Finding]
    checked: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "routine": self.routine,
            "checked": self.checked,
            "notes": self.notes,
            "findings": [f.as_dict() for f in self.findings],
        }


class Routine(Protocol):
    """What the nightly runner needs from a routine."""

    name: str

    def run(self) -> RoutineResult: ...
