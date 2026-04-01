"""Deterministic gates for the MindPattern autonomous harness.

These run WITHOUT an LLM. They are hard pass/fail checks that gate
every stage of the pipeline. If a gate fails, the ticket is rejected
immediately — no agent can override a deterministic gate.

Design principle: use Python for everything that CAN be deterministic.
Only use LLMs for things that require judgment (architecture analysis,
code review, security threat modeling). Never use an LLM to run tests,
check syntax, or validate JSON.
"""

import ast
import json
import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CONFIG_FILE = PROJECT_ROOT / "harness" / "config.json"

SECURITY_SENSITIVE_PATTERNS = [
    "social/approval.py", "social/posting.py", "memory/db.py",
    "orchestrator/sync.py", "dashboard/", "slack_bot/",
]

SECRET_PATTERNS = [
    r'(?i)(api_key|secret_key|private_key|password|token)\s*=\s*["\'][^"\']{8,}',
    r'(?i)Bearer\s+[a-zA-Z0-9\-_\.]{20,}',
    r'xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+',
]

DEBUG_PATTERNS = [
    r'^\s*import\s+pdb',
    r'^\s*breakpoint\(\)',
    r'^\s*import\s+ipdb',
]


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def _run(cmd: str, cwd: str | None = None) -> tuple[str, int]:
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        timeout=120, cwd=cwd or str(PROJECT_ROOT),
    )
    return result.stdout + result.stderr, result.returncode


# ── Pre-fix gates (run before fix agent starts) ──────────────────────

def validate_ticket(ticket_path: str) -> dict:
    """Validate ticket JSON is well-formed and complete."""
    failures = []

    try:
        ticket = json.loads(Path(ticket_path).read_text())
    except (json.JSONDecodeError, OSError) as e:
        return {"pass": False, "failures": [f"Invalid JSON: {e}"]}

    required = ["id", "title", "type", "priority", "status",
                 "requirements", "done_criteria", "tdd_spec", "files_to_modify"]
    for field in required:
        if field not in ticket:
            failures.append(f"Missing field: {field}")

    if ticket.get("tdd_spec"):
        tdd = ticket["tdd_spec"]
        if not tdd.get("test_file"):
            failures.append("tdd_spec.test_file is empty")
        if not tdd.get("tests_to_write"):
            failures.append("tdd_spec.tests_to_write is empty")

    if not ticket.get("files_to_modify"):
        failures.append("files_to_modify is empty")

    # Verify referenced files exist
    for f in ticket.get("files_to_modify", []):
        full = PROJECT_ROOT / f
        if not full.exists() and "test_" not in f:
            failures.append(f"File not found: {f}")

    return {"pass": len(failures) == 0, "failures": failures}


def check_security_sensitive(ticket_path: str) -> bool:
    """Deterministic check: does this ticket touch security-sensitive files?"""
    try:
        ticket = json.loads(Path(ticket_path).read_text())
    except (json.JSONDecodeError, OSError):
        return False

    config = _load_config()
    sensitive = config.get("security_sensitive_paths", SECURITY_SENSITIVE_PATTERNS)

    for f in ticket.get("files_to_modify", []):
        for pattern in sensitive:
            if pattern in f:
                return True
        # Also check for auth/token/key/secret in filename
        if re.search(r'auth|token|key|secret|password|cred', f, re.IGNORECASE):
            return True

    return False


def determine_review_depth(ticket_path: str) -> str:
    """Deterministic: map ticket type → review depth.

    Returns: 'eng-only', 'full', 'eng+security', or 'full+security'
    """
    try:
        ticket = json.loads(Path(ticket_path).read_text())
    except (json.JSONDecodeError, OSError):
        return "eng-only"

    ticket_type = ticket.get("type", "bug")
    is_sensitive = check_security_sensitive(ticket_path)

    if ticket_type in ("feature", "research"):
        return "full+security" if is_sensitive else "full"
    else:
        return "eng+security" if is_sensitive else "eng-only"


# ── Post-fix gates (run after fix agent, before review) ──────────────

def gate_tests_pass(cwd: str | None = None) -> dict:
    """Deterministic: run pytest. Hard fail if any test fails."""
    output, exit_code = _run("python3 -m pytest tests/ -x -q --tb=short", cwd=cwd)

    # Parse test counts
    passed = 0
    failed = 0
    for line in output.split("\n"):
        match = re.search(r'(\d+) passed', line)
        if match:
            passed = int(match.group(1))
        match = re.search(r'(\d+) failed', line)
        if match:
            failed = int(match.group(1))

    return {
        "pass": exit_code == 0,
        "total": passed + failed,
        "passed": passed,
        "failed": failed,
        "output": output[-1000:] if len(output) > 1000 else output,
    }


def gate_syntax_valid(changed_files: list[str], cwd: str | None = None) -> dict:
    """Deterministic: verify all changed .py files parse without syntax errors."""
    failures = []
    root = Path(cwd) if cwd else PROJECT_ROOT

    for f in changed_files:
        if not f.endswith(".py"):
            continue
        full = root / f
        if not full.exists():
            continue
        try:
            ast.parse(full.read_text())
        except SyntaxError as e:
            failures.append(f"{f}:{e.lineno}: {e.msg}")

    return {"pass": len(failures) == 0, "failures": failures}


def gate_no_secrets(changed_files: list[str], cwd: str | None = None) -> dict:
    """Deterministic: scan changed files for hardcoded secrets."""
    findings = []
    root = Path(cwd) if cwd else PROJECT_ROOT

    for f in changed_files:
        if not f.endswith(".py"):
            continue
        full = root / f
        if not full.exists():
            continue
        content = full.read_text()
        for i, line in enumerate(content.split("\n"), 1):
            for pattern in SECRET_PATTERNS:
                if re.search(pattern, line):
                    findings.append(f"{f}:{i}: possible hardcoded secret")

    return {"pass": len(findings) == 0, "findings": findings}


def gate_no_debug(changed_files: list[str], cwd: str | None = None) -> dict:
    """Deterministic: no debug statements left in changed files."""
    findings = []
    root = Path(cwd) if cwd else PROJECT_ROOT

    for f in changed_files:
        if not f.endswith(".py"):
            continue
        full = root / f
        if not full.exists():
            continue
        content = full.read_text()
        for i, line in enumerate(content.split("\n"), 1):
            for pattern in DEBUG_PATTERNS:
                if re.search(pattern, line):
                    findings.append(f"{f}:{i}: debug statement")

    return {"pass": len(findings) == 0, "findings": findings}


def gate_diff_scoped(ticket_path: str, branch: str, cwd: str | None = None) -> dict:
    """Deterministic: verify the diff only touches files in the ticket's files_to_modify."""
    try:
        ticket = json.loads(Path(ticket_path).read_text())
    except (json.JSONDecodeError, OSError):
        return {"pass": False, "failures": ["Cannot read ticket"]}

    allowed = set(ticket.get("files_to_modify", []))
    # Also allow the test file from tdd_spec
    tdd = ticket.get("tdd_spec", {})
    if tdd.get("test_file"):
        allowed.add(tdd["test_file"])

    output, _ = _run(f"git diff main...{branch} --name-only", cwd=cwd)
    changed = set(line.strip() for line in output.strip().split("\n") if line.strip())

    extra = changed - allowed
    if extra:
        return {
            "pass": False,
            "failures": [f"File modified outside ticket scope: {f}" for f in extra],
            "allowed": list(allowed),
            "changed": list(changed),
        }

    return {"pass": True, "allowed": list(allowed), "changed": list(changed)}


# ── Run all gates ────────────────────────────────────────────────────

def run_pre_fix_gates(ticket_path: str) -> dict:
    """Run all deterministic checks before the fix agent starts."""
    results = {}

    results["ticket_valid"] = validate_ticket(ticket_path)
    results["review_depth"] = determine_review_depth(ticket_path)
    results["security_sensitive"] = check_security_sensitive(ticket_path)

    all_pass = results["ticket_valid"]["pass"]
    return {"pass": all_pass, "results": results}


def run_post_fix_gates(ticket_path: str, branch: str, changed_files: list[str],
                       cwd: str | None = None) -> dict:
    """Run all deterministic checks after the fix agent commits."""
    results = {}

    results["tests"] = gate_tests_pass(cwd=cwd)
    results["syntax"] = gate_syntax_valid(changed_files, cwd=cwd)
    results["no_secrets"] = gate_no_secrets(changed_files, cwd=cwd)
    results["no_debug"] = gate_no_debug(changed_files, cwd=cwd)
    results["scope"] = gate_diff_scoped(ticket_path, branch, cwd=cwd)

    all_pass = all(r["pass"] for r in results.values())
    return {"pass": all_pass, "results": results}


# CLI interface
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m harness.gates <pre-fix|post-fix> <ticket_path> [branch] [files...]")
        sys.exit(1)

    cmd = sys.argv[1]
    ticket = sys.argv[2]

    if cmd == "pre-fix":
        result = run_pre_fix_gates(ticket)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["pass"] else 1)

    elif cmd == "post-fix":
        branch = sys.argv[3] if len(sys.argv) > 3 else "HEAD"
        files = sys.argv[4:] if len(sys.argv) > 4 else []
        result = run_post_fix_gates(ticket, branch, files)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["pass"] else 1)
