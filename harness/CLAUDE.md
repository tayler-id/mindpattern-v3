# MindPattern Autonomous Harness

Self-improving outer loop. Agents find issues, plan fixes with engineering rigor, implement with TDD, validate deterministically, review independently, and create PRs.

## Deterministic vs Agentic Boundary

**DETERMINISTIC (Python, no LLM):**
- Ticket validation (JSON schema, file existence)
- Security sensitivity detection (path matching)
- Review depth routing (type → depth mapping)
- Test execution (pytest)
- Syntax validation (ast.parse)
- Secret scanning (regex)
- Debug statement detection (regex)
- Diff scope checking (git diff vs allowed files)
- Ticket lifecycle (pick, mark, decay, archive)
- Slack notifications (API calls)
- Audit logging (JSONL append)

**AGENTIC (Opus 4.6, requires judgment):**
- Scout: finding issues that require reading + understanding code
- Research: searching the web for ideas
- Plan: architecture analysis, error mapping, threat modeling
- Fix: writing tests + implementation
- Review: code quality assessment, specialist analysis

**Rule: if Python can do it reliably, Python does it. LLMs only for judgment.**

## Pipeline Flow

```
TICKET CREATED
     │
     ▼
┌─ DETERMINISTIC: validate_ticket() ─────────────────────┐
│  JSON schema valid? files_to_modify exist?              │
│  FAIL → reject ticket immediately                       │
└─────────────────────────────────────────────────────────┘
     │ PASS
     ▼
┌─ DETERMINISTIC: determine_review_depth() ──────────────┐
│  Bug/improvement → eng-only                            │
│  Feature/research → full (CEO + eng)                   │
│  Touches auth/API/data → +security                     │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─ AGENTIC: Plan Agent (Opus, worktree) ─────────────────┐
│  Reads gstack skill files for methodology:              │
│  • /plan-eng-review → architecture, errors, tests       │
│  • /plan-ceo-review → premise, alternatives (features)  │
│  • /cso → OWASP, STRIDE (if security-sensitive)         │
│  Writes: harness/plans/<ticket-id>.md                   │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─ AGENTIC: Fix Agent (Opus, worktree) ──────────────────┐
│  Reads ticket + plan. TDD: tests first, then code.      │
│  Creates branch: harness/<ticket-id>                     │
│  Commits.                                                │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─ DETERMINISTIC: post-fix gates ────────────────────────┐
│  gate_tests_pass()      → pytest full suite             │
│  gate_syntax_valid()    → ast.parse all changed files   │
│  gate_no_secrets()      → regex scan for secrets        │
│  gate_no_debug()        → no pdb/breakpoint left        │
│  gate_diff_scoped()     → only ticket files modified    │
│  ALL must pass. Any failure → ticket rejected.          │
└─────────────────────────────────────────────────────────┘
     │ ALL PASS
     ▼
┌─ AGENTIC: Review Agent (Opus, SEPARATE worktree) ──────┐
│  3 specialist subagents in parallel:                     │
│  • Testing specialist: coverage gaps, edge cases         │
│  • Security specialist: OWASP checks on the diff        │
│  • Maintainability specialist: DRY, naming, complexity   │
│  Quality score computed. >= 7 = PASS.                    │
│  PASS → push branch, create PR with evidence             │
│  FAIL → reject with detailed findings                    │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─ DETERMINISTIC: CI (GitHub Actions) ───────────────────┐
│  pytest on Ubuntu. Hard pass/fail on PR.                │
└─────────────────────────────────────────────────────────┘
     │
     ▼
  Human merges or closes → feedback.json → scout learns

## Claude Code Hooks

hooks fire on every tool call:

**PreToolUse (Bash):** `harness/hooks/pre_commit_gate.py`
- Blocks git commit if: syntax errors, hardcoded secrets, debug statements
- Only fires in harness worktrees (checks cwd)

**PostToolUse (Bash):** `harness/hooks/post_tool_audit.py`
- Logs every tool call to `harness/audit.jsonl`
- Deterministic audit trail, no LLM

## Ticket JSON Schema

```json
{
  "id": "YYYY-MM-DD-NNN",
  "title": "Short description",
  "type": "bug|improvement|feature|research",
  "source": "scout|research",
  "priority": "P1|P2|P3",
  "status": "open|in_progress|done|failed|held",
  "description": "Detailed description",
  "requirements": ["..."],
  "done_criteria": ["..."],
  "tdd_spec": {
    "test_file": "tests/test_something.py",
    "tests_to_write": ["test_name"]
  },
  "files_to_modify": ["path/to/file.py"],
  "context": "Additional context",
  "created_at": "ISO-8601",
  "expires_at": "ISO-8601 (+ 7 days)",
  "feedback_history": []
}
```

## gstack Skills Used

| Stage | Skill | When | What it provides |
|-------|-------|------|------------------|
| Plan | `/plan-eng-review` | All tickets | Architecture, error paths, test plan |
| Plan | `/plan-ceo-review` | Features/research | Premise challenge, alternatives |
| Plan | `/cso` | Security-sensitive files | OWASP Top 10, STRIDE threats |
| Review | `/review` | All PRs | Specialist subagents (testing, security, maintainability) |
