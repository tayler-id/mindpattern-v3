"""Deterministic expert boundary for Rabbit Hole site content.

The live expert/provider path is intentionally not implemented here. Focused
tests and dry-runs use fake experts so this module never calls models,
network, Slack, social APIs, email, Fly, Vercel, or the daily pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


DEFAULT_SITE_EXPERT_ROLES = [
    "Assignment Editor",
    "Graph Cartographer",
    "Domain Expert",
    "Skeptic and Fact Checker",
    "Narrative Editor",
    "Source Librarian",
    "GEO and Agent-Web Editor",
    "Website Publisher",
]


class SiteContentExpert(Protocol):
    role: str

    def run(self, graph_pack: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class FakeSiteContentExpert:
    """Deterministic test/dry-run expert implementation."""

    role: str

    def run(self, graph_pack: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        candidate_id = graph_pack.get("candidate_id", "unknown")
        evidence_count = len(graph_pack.get("primary_evidence") or [])
        source_count = len(graph_pack.get("source_refs") or [])
        edge_count = len(graph_pack.get("graph_edges") or [])
        return {
            "role": self.role,
            "provider": "fake",
            "status": "ok" if evidence_count and source_count and edge_count else "degraded",
            "candidate_id": candidate_id,
            "summary": (
                f"{self.role} reviewed {candidate_id} with "
                f"{evidence_count} primary evidence item(s), "
                f"{source_count} source(s), and {edge_count} graph edge(s)."
            ),
            "signals": {
                "evidence_count": evidence_count,
                "source_count": source_count,
                "edge_count": edge_count,
                "date": context.get("date", ""),
            },
        }


def get_site_experts(
    *,
    provider: str = "fake",
    live_config: dict[str, Any] | None = None,
) -> list[SiteContentExpert]:
    """Return site experts, falling back closed to fake deterministic experts."""
    if provider != "fake" and not live_config:
        return [FakeSiteContentExpert(role=role) for role in DEFAULT_SITE_EXPERT_ROLES]
    return [FakeSiteContentExpert(role=role) for role in DEFAULT_SITE_EXPERT_ROLES]


def run_site_expert_loop(
    graph_pack: dict[str, Any],
    *,
    experts: list[SiteContentExpert] | None = None,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run deterministic experts over a graph pack."""
    ctx = context or {}
    expert_list = experts or get_site_experts(provider="fake")
    return [expert.run(graph_pack, ctx) for expert in expert_list]
