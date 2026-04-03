"""Tests for orchestrator/pipeline.py phase transitions and state machine."""

import pytest

from orchestrator.pipeline import (
    CRITICAL_PHASES,
    PHASE_ORDER,
    SKIPPABLE_PHASES,
    TERMINAL_PHASES,
    VALID_TRANSITIONS,
    Phase,
    PipelineRun,
)


def test_all_phases_in_enum():
    """Phase enum has all 12 execution phases plus COMPLETED and FAILED."""
    expected = {
        "INIT", "TREND_SCAN", "RESEARCH", "SYNTHESIS",
        "DELIVER", "LEARN", "SOCIAL", "ENGAGEMENT",
        "EVOLVE", "IDENTITY", "MIRROR", "SYNC",
        "COMPLETED", "FAILED",
    }
    actual = {p.name for p in Phase}
    assert actual == expected


def test_phase_order_sequence():
    """PHASE_ORDER follows the documented execution sequence."""
    expected_order = [
        Phase.INIT, Phase.TREND_SCAN, Phase.RESEARCH, Phase.SYNTHESIS,
        Phase.DELIVER, Phase.LEARN, Phase.SOCIAL, Phase.ENGAGEMENT,
        Phase.EVOLVE, Phase.IDENTITY, Phase.MIRROR, Phase.SYNC,
        Phase.COMPLETED,
    ]
    assert PHASE_ORDER == expected_order


def test_critical_phases():
    """CRITICAL_PHASES contains RESEARCH and SYNTHESIS."""
    assert Phase.RESEARCH in CRITICAL_PHASES
    assert Phase.SYNTHESIS in CRITICAL_PHASES
    # Only these two should be critical
    assert CRITICAL_PHASES == {Phase.RESEARCH, Phase.SYNTHESIS}


def test_skippable_phases_excludes_critical():
    """No phase appears in both SKIPPABLE_PHASES and CRITICAL_PHASES."""
    overlap = SKIPPABLE_PHASES & CRITICAL_PHASES
    assert overlap == set(), f"Phases in both skippable and critical: {overlap}"


def test_no_duplicate_phases_in_order():
    """PHASE_ORDER has no duplicate phases."""
    assert len(PHASE_ORDER) == len(set(PHASE_ORDER))


def test_failed_not_in_phase_order():
    """FAILED is a terminal state, not part of the normal execution order."""
    assert Phase.FAILED not in PHASE_ORDER


def test_valid_transitions_allow_next_phase():
    """Each phase can transition to the next phase in order."""
    for i, phase in enumerate(PHASE_ORDER[:-1]):
        next_phase = PHASE_ORDER[i + 1]
        assert next_phase in VALID_TRANSITIONS[phase], (
            f"{phase.value} should be able to transition to {next_phase.value}"
        )


def test_valid_transitions_allow_failed():
    """Every non-terminal phase can transition to FAILED."""
    for phase in PHASE_ORDER[:-1]:
        assert Phase.FAILED in VALID_TRANSITIONS[phase]


def test_transition_rejects_backward():
    """Cannot go backward in the phase sequence."""
    run = PipelineRun("test", "user1", "2026-04-01")
    run.transition(Phase.TREND_SCAN)
    with pytest.raises(ValueError, match="Invalid transition"):
        run.transition(Phase.INIT)


def test_transition_rejects_from_terminal():
    """Cannot transition out of a terminal phase."""
    run = PipelineRun("test", "user1", "2026-04-01")
    run.current_phase = Phase.COMPLETED
    with pytest.raises(ValueError, match="terminal phase"):
        run.transition(Phase.INIT)


def test_fail_critical_phase_sets_failed():
    """Failing a critical phase moves pipeline to FAILED."""
    run = PipelineRun("test", "user1", "2026-04-01")
    run.current_phase = Phase.RESEARCH
    run.fail_phase(Phase.RESEARCH, "agent crashed")
    assert run.current_phase == Phase.FAILED


def test_fail_skippable_phase_adds_warning():
    """Failing a skippable phase adds a warning but doesn't fail the pipeline."""
    run = PipelineRun("test", "user1", "2026-04-01")
    run.fail_phase(Phase.INIT, "minor issue")
    assert run.current_phase != Phase.FAILED
    assert len(run.warnings) == 1


def test_next_phase_returns_correct_successor():
    """next_phase property returns the next phase in sequence."""
    run = PipelineRun("test", "user1", "2026-04-01")
    assert run.next_phase == Phase.TREND_SCAN
    run.transition(Phase.TREND_SCAN)
    assert run.next_phase == Phase.RESEARCH


def test_next_phase_none_when_terminal():
    """next_phase returns None for terminal phases."""
    run = PipelineRun("test", "user1", "2026-04-01")
    run.current_phase = Phase.FAILED
    assert run.next_phase is None
