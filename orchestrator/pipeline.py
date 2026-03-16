"""Pipeline state machine for deterministic phase execution.

Each pipeline run progresses through a fixed sequence of phases.
Python controls the state transitions — the LLM never decides what phase comes next.
"""

import enum
import uuid
from datetime import datetime


class Phase(enum.Enum):
    """Pipeline phases in execution order."""
    INIT = "init"
    TREND_SCAN = "trend_scan"
    RESEARCH = "research"
    SYNTHESIS = "synthesis"
    DELIVER = "deliver"
    LEARN = "learn"
    SOCIAL = "social"
    ENGAGEMENT = "engagement"
    EVOLVE = "evolve"
    MIRROR = "mirror"
    SYNC = "sync"
    COMPLETED = "completed"
    FAILED = "failed"


# Strict forward-only transitions
PHASE_ORDER = [
    Phase.INIT,
    Phase.TREND_SCAN,
    Phase.RESEARCH,
    Phase.SYNTHESIS,
    Phase.DELIVER,
    Phase.LEARN,
    Phase.SOCIAL,
    Phase.ENGAGEMENT,
    Phase.EVOLVE,
    Phase.MIRROR,
    Phase.SYNC,
    Phase.COMPLETED,
]

TERMINAL_PHASES = {Phase.COMPLETED, Phase.FAILED}

# Which phases are critical (pipeline fails if they fail)
CRITICAL_PHASES = {Phase.RESEARCH, Phase.SYNTHESIS}

# Which phases are skippable (pipeline continues if they fail)
SKIPPABLE_PHASES = {
    Phase.INIT, Phase.TREND_SCAN, Phase.DELIVER,
    Phase.LEARN, Phase.SOCIAL, Phase.ENGAGEMENT,
    Phase.EVOLVE, Phase.MIRROR, Phase.SYNC,
}

VALID_TRANSITIONS: dict[Phase, set[Phase]] = {}
for i, phase in enumerate(PHASE_ORDER[:-1]):
    next_phase = PHASE_ORDER[i + 1]
    VALID_TRANSITIONS[phase] = {next_phase, Phase.FAILED}
# Any phase can also skip to COMPLETED (for partial runs)
for phase in PHASE_ORDER[:-1]:
    VALID_TRANSITIONS[phase].add(Phase.COMPLETED)


class PipelineRun:
    """Tracks a single pipeline run through its phase lifecycle."""

    def __init__(self, pipeline_type: str, user_id: str, run_date: str):
        self.run_id = f"{pipeline_type}-{run_date}-{uuid.uuid4().hex[:6]}"
        self.pipeline_type = pipeline_type
        self.user_id = user_id
        self.run_date = run_date
        self.current_phase = Phase.INIT
        self.started_at = datetime.now().isoformat()
        self.warnings: list[str] = []
        self.phase_results: dict[str, dict] = {}
        self._phase_start_time: datetime | None = None

    def transition(self, new_phase: Phase) -> bool:
        """Transition to a new phase. Returns True if valid, raises ValueError if not."""
        if self.current_phase in TERMINAL_PHASES:
            raise ValueError(
                f"Cannot transition from terminal phase {self.current_phase.value}"
            )

        valid = VALID_TRANSITIONS.get(self.current_phase, set())
        if new_phase not in valid:
            raise ValueError(
                f"Invalid transition: {self.current_phase.value} → {new_phase.value}. "
                f"Valid: {[p.value for p in valid]}"
            )

        self.current_phase = new_phase
        self._phase_start_time = datetime.now()
        return True

    def complete_phase(self, phase: Phase, result: dict | None = None):
        """Record a phase completion with optional result data."""
        self.phase_results[phase.value] = {
            "status": "completed",
            "result": result or {},
            "completed_at": datetime.now().isoformat(),
        }

    def fail_phase(self, phase: Phase, error: str):
        """Record a phase failure."""
        self.phase_results[phase.value] = {
            "status": "failed",
            "error": error,
            "failed_at": datetime.now().isoformat(),
        }
        if phase in CRITICAL_PHASES:
            self.current_phase = Phase.FAILED
        else:
            self.warnings.append(f"{phase.value}: {error}")

    def fail(self, error: str):
        """Mark entire pipeline as failed."""
        self.current_phase = Phase.FAILED
        self.phase_results["_pipeline"] = {
            "status": "failed",
            "error": error,
            "failed_at": datetime.now().isoformat(),
        }

    @property
    def is_terminal(self) -> bool:
        return self.current_phase in TERMINAL_PHASES

    @property
    def next_phase(self) -> Phase | None:
        """Get the next phase in sequence, or None if terminal."""
        if self.is_terminal:
            return None
        try:
            idx = PHASE_ORDER.index(self.current_phase)
            return PHASE_ORDER[idx + 1] if idx + 1 < len(PHASE_ORDER) else None
        except ValueError:
            return None

    def summary(self) -> dict:
        """Return a summary of the pipeline run state."""
        return {
            "run_id": self.run_id,
            "pipeline_type": self.pipeline_type,
            "user_id": self.user_id,
            "run_date": self.run_date,
            "current_phase": self.current_phase.value,
            "started_at": self.started_at,
            "warnings": self.warnings,
            "phases_completed": [
                k for k, v in self.phase_results.items()
                if v.get("status") == "completed"
            ],
        }
