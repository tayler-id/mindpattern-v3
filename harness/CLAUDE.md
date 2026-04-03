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
- Knowledge graph validation (wiki-link resolution, section checks, index completeness, code ref enforcement)
- Knowledge graph search (5-tier: exact → stem → tail → subsequence → Levenshtein)
- Knowledge graph evolution (auto-update after harness stages)
- Code↔docs sync detection (git diff analysis)

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

**PostToolUse (Write/Edit):** `harness/hooks/knowledge_gate.py`
- Validates knowledge graph integrity after .py file edits
- Runs 4 validation passes: refs, sections, index, code_refs
- Detects underdocumented code changes (warns if code_lines >> knowledge_lines)
- Warning-only — does not block

## Knowledge Graph

31 interconnected markdown files in `harness/knowledge/`. Wiki-link syntax `[[slug]]` creates edges. Supports section-level refs: `[[orchestrator/runner#Error Handling]]`.

**Architecture** (`harness/knowledge_sections.py` + `harness/knowledge_graph.py`):
- `knowledge_sections.py`: Pure algorithms — section tree parser, suffix-index builder, 5-tier fuzzy search, Levenshtein distance, code-ref scanner. No I/O.
- `knowledge_graph.py`: I/O layer — file reading, validation orchestration, CLI, evolve/summary.

**Section tree parser**: Stack-based algorithm parses markdown headings into a hierarchy with IDs like `orchestrator/runner#Key Functions#run_single_agent`. Skips headings inside fenced code blocks and YAML frontmatter.

**Suffix index**: Maps all trailing path suffixes to file paths for case-insensitive, underscore-tolerant ref resolution. Detects ambiguity when multiple files share a suffix.

**5-tier search** (`find_sections`):
1. Exact match on full section ID
2. File stem expansion via suffix index
3. Subsection tail match (query = last segment)
4. Subsequence match (query segments in order within ID)
5. Levenshtein fuzzy match (threshold: 40% of max length)

**4-pass validation** (`check`):
1. `check_refs` — all wiki-links resolve to real files and sections
2. `check_sections` — every section has a leading paragraph ≤ 250 chars
3. `check_index` — INDEX.md has entries for all files, no stale entries
4. `check_code_refs` — `# @know: [[slug]]` comments resolve; `require-code-mention` enforced

**Code references**: Add `# @know: [[slug#Section]]` in Python source. Scanner uses ripgrep (fast) with pathlib fallback.

**CLI**: `python3 -m harness.knowledge_graph check|search|expand|parse|locate|refs|list`

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
