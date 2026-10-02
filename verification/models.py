"""Data contracts shared by the verification CLI and worker."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Feature:
    id: str
    description: str
    routes: tuple[str, ...]
    verifier: str
    limits: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RequestResult:
    method: str
    path: str
    status: int
    body: Any
    elapsed_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AssertionResult:
    name: str
    passed: bool
    expected: Any
    observed: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
