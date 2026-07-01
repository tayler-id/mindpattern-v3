from pathlib import Path

from orchestrator.site_content_engine import build_graph_pack, load_fixture_cases
from orchestrator.site_experts import (
    DEFAULT_SITE_EXPERT_ROLES,
    FakeSiteContentExpert,
    get_site_experts,
    run_site_expert_loop,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "site_content" / "graph_pack_cases.json"


def _graph_pack():
    payload = load_fixture_cases(FIXTURE_PATH)
    candidate = next(case for case in payload["cases"] if case["id"] == "openai-agent-runtime-reliability")
    return build_graph_pack(candidate, date="2026-07-01", user="ramsay")


def test_fake_expert_loop_is_deterministic_and_role_explicit():
    experts = [FakeSiteContentExpert(role=role) for role in DEFAULT_SITE_EXPERT_ROLES]

    first = run_site_expert_loop(_graph_pack(), experts=experts, context={"date": "2026-07-01"})
    second = run_site_expert_loop(_graph_pack(), experts=experts, context={"date": "2026-07-01"})

    assert [result["role"] for result in first] == DEFAULT_SITE_EXPERT_ROLES
    assert first == second
    assert all(result["status"] == "ok" for result in first)
    assert all(result["provider"] == "fake" for result in first)
    assert all("Slack" not in result["summary"] for result in first)


def test_missing_live_provider_config_falls_back_to_fake_experts():
    experts = get_site_experts(provider="live", live_config=None)

    assert [expert.role for expert in experts] == DEFAULT_SITE_EXPERT_ROLES
    assert all(isinstance(expert, FakeSiteContentExpert) for expert in experts)
