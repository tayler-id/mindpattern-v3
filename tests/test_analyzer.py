"""Tests for self-optimization analyzer."""
import json
from pathlib import Path

from orchestrator.pipeline import Phase, PHASE_ORDER, SKIPPABLE_PHASES


# ── Pipeline phase tests ──────────────────────────────────────────

def test_analyze_phase_exists():
    assert hasattr(Phase, "ANALYZE")
    assert Phase.ANALYZE.value == "analyze"


def test_analyze_in_phase_order():
    order = [p.value for p in PHASE_ORDER]
    evolve_idx = order.index("evolve")
    analyze_idx = order.index("analyze")
    mirror_idx = order.index("mirror")
    assert evolve_idx < analyze_idx < mirror_idx


def test_analyze_is_skippable():
    assert Phase.ANALYZE in SKIPPABLE_PHASES
