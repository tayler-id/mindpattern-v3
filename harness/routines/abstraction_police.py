"""abstraction-police — import edges vs layers.toml.

The plan ranks this highest-value because it catches a class of bug the test
suite structurally cannot: locally ``harness/`` is always importable, in the
Fly container it does not exist. A module-level ``import harness`` inside
``dashboard/`` or ``slack_bot/`` passes every local test and crashes the
deployed app.

Signal: deterministic (harness.layers.check_layers). No model involved.
"""

from __future__ import annotations

from harness.layers import check_layers
from harness.routines.base import Finding, RoutineResult
from harness.sandbox import assert_sandbox

NAME = "abstraction-police"

# The repro every layer finding shares: the checker itself. It fails while any
# violation stands and passes once the import is removed or declared.
REPRO = ".venv/bin/python -m harness.layers check"


class AbstractionPolice:
    name = NAME

    def run(self) -> RoutineResult:
        assert_sandbox()
        result = check_layers()

        findings = []
        for violation in result["violations"]:
            container = violation["kind"] == "container-module-level"
            findings.append(Finding(
                routine=NAME,
                kind=violation["kind"],
                title=(
                    f"{violation['src']} imports {violation['dst']} "
                    f"({violation['level']}-level)"
                ),
                detail=(
                    f"{violation['file']}:{violation['line']} imports "
                    f"{violation['dst']} at {violation['level']} level. "
                    + (
                        f"{violation['src']} ships in the Fly container and "
                        f"{violation['dst']} does not, so this import passes "
                        "every local test and fails in production. Fix by "
                        "deferring the import inside the function and adding an "
                        "[[allow.deferred]] entry, or by removing the dependency."
                        if container else
                        "This cross-package edge is not declared in layers.toml. "
                        "Either remove it or declare it deliberately."
                    )
                ),
                file=violation["file"],
                line=violation["line"],
                repro=REPRO,
                truth_rows=[{
                    "input": f"{violation['file']}:{violation['line']}",
                    "expected": "layers check passes",
                    "pre": "VIOLATION",
                    "post": "pass",
                }],
                severity="high" if container else "normal",
            ))

        return RoutineResult(
            routine=NAME,
            findings=findings,
            checked=result["edges_checked"],
            notes=[f"{result['edges_checked']} cross-package imports checked"],
        )
