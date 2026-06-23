"""Claude CLI dispatch for research agents.

Key change from v2: instead of one monolithic claude -p call that orchestrates
everything, we make individual per-agent calls via concurrent.futures. Each agent
gets a focused prompt with its context. Python controls the orchestration.
"""

import json
import logging
import os
import random
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.claude_cli import kill_process_group, run_claude_process
from memory.embeddings import embed_texts
from . import router

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SOCIAL_DRAFTS_DIR = PROJECT_ROOT / "data" / "social-drafts"

# Pipeline date — set by runner before dispatching agents
_pipeline_date: str | None = None


def _dry_run_enabled() -> bool:
    """Return True when CLI/model calls must be skipped."""
    return os.environ.get("MP_DRY_RUN") == "1"


def _dry_run_finding(agent_name: str) -> dict:
    """Build one deterministic placeholder finding for dry-run orchestration."""
    return {
        "title": f"Dry-run finding for {agent_name}",
        "summary": (
            "Placeholder finding generated locally because MP_DRY_RUN=1. "
            "No Claude call or web research was performed."
        ),
        "importance": "low",
        "category": "dry-run",
        "source_url": None,
        "source_name": "Dry Run",
    }


def _dry_run_prompt_output(task_type: str) -> str:
    """Return deterministic stdout for dry-run Claude prompt calls."""
    if task_type == "feedback_processor":
        return json.dumps({"preferences": []})
    if task_type == "identity":
        return json.dumps({
            "soul": {"action": "none"},
            "user": {"action": "none"},
            "voice": {"action": "none"},
            "decisions": {"action": "none"},
        })
    if task_type == "learnings_update":
        return "# Learnings\n\nDry-run: Claude updater skipped.\n"
    if task_type == "synthesis_pass1":
        return "Dry-run story selection. Use placeholder synthesis output."
    if task_type == "synthesis_pass2":
        date_label = _pipeline_date or "unknown date"
        return f"# Dry-Run Report - {date_label}\n\nThis is a dry-run placeholder.\n"
    return json.dumps({"dry_run": True, "task_type": task_type})


def _dry_run_file_payload(task_type: str) -> dict:
    """Return deterministic structured output for file-writing dry-run agents."""
    return {"dry_run": True, "task_type": task_type}


def set_pipeline_date(date_str: str) -> None:
    """Set the pipeline date so subprocess env vars include it."""
    global _pipeline_date
    _pipeline_date = date_str


def _agent_env(agent_name: str) -> dict[str, str]:
    """Build environment dict for a claude -p subprocess.

    Inherits the parent process environment and adds MINDPATTERN_AGENT,
    MINDPATTERN_DATE, and MINDPATTERN_VAULT so the SessionEnd hook can
    capture the transcript into the correct agent folder.
    """
    env = {**os.environ}
    env["MINDPATTERN_AGENT"] = agent_name
    if _pipeline_date:
        env["MINDPATTERN_DATE"] = _pipeline_date
    vault = PROJECT_ROOT / "data" / "ramsay" / "mindpattern"
    env["MINDPATTERN_VAULT"] = str(vault)
    return env

# Tools each research agent is allowed to use. Research agents ingest
# scraped web content — an injected instruction must never reach a shell
# or spawn subagents, so Bash and Agent are NOT in this list (audit C6).
AGENT_ALLOWED_TOOLS = [
    "WebSearch", "WebFetch", "Read", "Glob", "Grep",
]


@dataclass
class AgentResult:
    """Result from a single agent execution."""
    agent_name: str
    findings: list[dict] = field(default_factory=list)
    raw_output: str = ""
    exit_code: int = 0
    duration_ms: int = 0
    killed_by_timeout: bool = False
    error: str | None = None
    classification: str | None = None


def load_user_config(user_id: str) -> dict:
    """Load user config from users.json."""
    users_path = PROJECT_ROOT / "users.json"
    with open(users_path) as f:
        users = json.load(f)
    for user in users.get("users", []):
        if user.get("id") == user_id:
            return user
    raise ValueError(f"User {user_id} not found in users.json")


def load_global_config() -> dict:
    """Load global config from config.json."""
    config_path = PROJECT_ROOT / "config.json"
    with open(config_path) as f:
        return json.load(f)


def get_agent_list(user_id: str, vertical: str = "ai-tech") -> tuple[list[str], Path]:
    """Get the list of active agents and their directory.

    Checks agent-overrides first, falls back to vertical agents.
    Returns (agent_names, agents_dir).
    """
    overrides_dir = PROJECT_ROOT / "data" / user_id / "agent-overrides"
    agents_json = overrides_dir / "agents.json"

    if agents_json.exists():
        with open(agents_json) as f:
            data = json.load(f)
        return data.get("agents", []), overrides_dir

    # Fall back to vertical agents
    vertical_dir = PROJECT_ROOT / "verticals" / vertical / "agents"
    agents = [p.stem for p in vertical_dir.glob("*.md")]
    return agents, vertical_dir


def get_agent_skill_path(agent_name: str, user_id: str, vertical: str = "ai-tech") -> Path:
    """Resolve the skill file path for an agent (override or vertical)."""
    override = PROJECT_ROOT / "data" / user_id / "agent-overrides" / f"{agent_name}.md"
    if override.exists():
        return override
    return PROJECT_ROOT / "verticals" / vertical / "agents" / f"{agent_name}.md"


def build_agent_prompt(
    agent_name: str,
    user_id: str,
    date_str: str,
    soul_path: Path,
    agent_skill_path: Path,
    context: str,
    trends: list[dict] | None = None,
    preflight_items: list[dict] | None = None,
    already_covered: list[dict] | None = None,
    identity_dir: Path | None = None,
) -> str:
    """Build the prompt for a single research agent.

    Structure (IFScale: critical rules at start AND end):
    1. Critical output rules (JSON schema)
    2. SOUL identity
    3. Agent skill definition
    4. Dynamic context (date, trends, memory context)
    5. Novelty requirement
    6. Phase 1 (evaluate preflight) + Phase 2 (explore) — or legacy SMTL
    7. Critical output rules repeated
    """
    soul_content = soul_path.read_text() if soul_path.exists() else ""
    skill_content = agent_skill_path.read_text() if agent_skill_path.exists() else ""

    # Load identity files from vault if identity_dir provided
    user_content = ""
    if identity_dir:
        vault_soul = identity_dir / "soul.md"
        if vault_soul.exists():
            soul_content = vault_soul.read_text()  # Override verticals version
        vault_user = identity_dir / "user.md"
        if vault_user.exists():
            user_content = vault_user.read_text()

    trends_section = ""
    if trends:
        from preflight.trends import format_trends_for_agents
        trends_section = "\n" + format_trends_for_agents(trends) + "\n"

    # Build preflight sections if data available
    preflight_section = ""
    if preflight_items:
        new_items = [i for i in preflight_items if not i.get("already_covered")]
        covered_items = already_covered or [i for i in preflight_items if i.get("already_covered")]

        # Phase 1: Evaluate preflight data
        items_md = []
        for idx, item in enumerate(new_items, 1):
            metrics_str = ""
            if item.get("metrics"):
                parts = [f"{k}={v}" for k, v in item["metrics"].items() if v]
                if parts:
                    metrics_str = f" ({', '.join(parts)})"
            items_md.append(
                f"{idx}. **[{item['source'].upper()}]** [{item.get('source_name', '')}] "
                f"{item['title']}\n"
                f"   URL: {item['url']}\n"
                f"   {item.get('content_preview', '')[:200]}{metrics_str}"
            )

        covered_md = []
        for item in (covered_items or [])[:20]:
            mi = item.get("match_info") or {}
            covered_md.append(
                f"- ~~{item['title']}~~ — covered by {mi.get('matched_agent', '?')} "
                f"on {mi.get('matched_date', '?')} (sim={mi.get('similarity', 0):.2f})"
            )

        nl = "\n"
        preflight_section = f"""

---

## Phase 1: Evaluate Pre-Fetched Data

Below are {len(new_items)} NEW items pre-fetched from your domain sources.

Select ALL qualifying new items as findings (minimum 15, target 18-20). For each:
- Verify the content is real and recent (not old news resurfacing)
- Write a 2-3 sentence summary with specific details (names, numbers, dates)
- Rate importance (high/medium/low)
- Include the source_url from the preflight data

{nl.join(items_md)}

### ALREADY COVERED (skip unless major update)

{nl.join(covered_md) if covered_md else 'None.'}

---

## Phase 2: Explore Beyond Preflight

The preflight data covers known sources. Now find what it MISSED.
Use only these allowed direct research tools to discover 3-5 additional findings:

- WebSearch for discovery across the public web
- WebFetch for deep reads of known URLs
- Read, Glob, and Grep only for local repository or vault context

Look for:
- Stories that broke in the last 6 hours (too recent for RSS/feeds)
- Primary sources not in our feed list
- Reactions and follow-ups to stories in the preflight data

Do not use shell commands, external CLIs, or network commands.
Do not spawn subagents; do the verification directly with the allowed tools.

Target: 20-25 total findings (15-20 from Phase 1 + 3-5 from Phase 2).

"""

    # Old search instructions — only used when no preflight data
    search_section = ""
    if not preflight_items:
        search_section = """
---

## Search Instructions (SMTL)

PHASE A: Execute ALL search queries. Collect all results. Do NOT evaluate yet.
PHASE B: Now reason over collected evidence. Score each finding.
PHASE C: Filter against the Recent Findings list. Remove anything already covered.

For each finding evaluation, use max 5 words per reasoning step.
Do not explain your full reasoning — just output the finding.
"""

    prompt = f"""CRITICAL: Output ONLY valid JSON matching this schema. No markdown, no commentary.
{{
  "findings": [
    {{
      "title": "string",
      "summary": "string (2-3 sentences)",
      "importance": "high|medium|low",
      "category": "string",
      "source_url": "string (full URL)",
      "source_name": "string",
      "date_found": "{date_str}"
    }}
  ]
}}

---

{soul_content}

---

{user_content}

---

{skill_content}

---

## Research Context — {date_str}
{trends_section}
{context}

---

## NOVELTY REQUIREMENT (CRITICAL)

You MUST find NEW content that is NOT in the "Recent Findings" list above.
The recent findings list covers the LAST 10 DAYS of published newsletters.
If a topic, company, product, or event was covered in ANY of the last 10 days,
DO NOT include it unless ALL of these are true:
- There is genuinely new data, a new announcement, or a material update
- The new information changes the story meaningfully (not just "more coverage")
- You can cite a specific new source published in the last 48 hours

"More coverage of the same story" is NOT new. "A blog post summarizing what
we already reported" is NOT new. "An old paper trending on social media" is NOT new.

Search for what happened in the LAST 48 HOURS. Prioritize:
- Brand new announcements, launches, releases from the last 24 hours
- Breaking developments not yet widely covered
- Primary sources (official blogs, papers, repos) over secondary coverage
- ArXiv papers must have been published in the last 7 days (check the arXiv ID date prefix)

Every finding you return must pass this test: "Would someone who read
the last 10 issues of this newsletter learn something genuinely NEW from this?"

---

## RESEARCH METHODOLOGY

Follow this structured approach for high-quality findings:

### Source Verification (REQUIRED)
- For every major finding, verify the claim from at least 2 independent sources
- If you can only find a single source, mark importance as "low"
- Prefer primary sources (official blogs, release notes, papers) over secondary coverage (news articles, rewrites)
- Cross-reference metrics: if a source claims "10K stars," verify on the actual GitHub repo

### Competing Hypotheses
When evaluating a story's importance, consider:
- What's the strongest counter-argument to this being important?
- Is this a genuine development or marketing hype?
- Could this be old news resurfacing? Check the actual publication date, not when it was shared.

### Tool Boundary
Use only the direct tools allowed for this research subprocess: WebSearch,
WebFetch, Read, Glob, and Grep. Do not use shell commands, external CLIs,
write/edit tools, or subagents.

### Self-Critique Gate (MANDATORY — do this BEFORE outputting JSON)
Review EVERY finding against these checks before including it:

1. **Recency**: Is the primary source from the last 48 hours? If older, DROP IT.
2. **10-Day Dedup**: Was this topic covered in any newsletter in the last 10 days (check the Recent Findings list)? If yes and no genuinely new data, DROP IT.
3. **Source Quality**: Is this from a primary source or a rewrite? If rewrite with no new information, DROP IT.
4. **Verification**: Can you verify this from at least one other source? If single-source, mark importance "low".
5. **Analysis**: Did you add your own analysis, or just restate the headline? Add what it means for builders.
6. **ArXiv Date Check**: If citing an arXiv paper, verify the ID date prefix matches the last 7 days (e.g., "2603" = March 2026). Papers from months ago are NOT new.

Drop any finding that fails checks 1, 2, or 3. Downgrade any finding that fails checks 4 or 5.
{preflight_section}{search_section}
---

CRITICAL REMINDER: Output ONLY the JSON object with "findings" array. No other text.
"""
    return prompt


# Failure classes that are transient/server-side and worth retrying. A 529
# (overloaded_error), 429 (rate_limit_error), or 5xx is recoverable — Anthropic
# marks them retryable — so we re-invoke the same claude CLI call (staying on
# Tayler's subscription, NOT the paid API) with backoff + full jitter.
_TRANSIENT_CLASSIFICATIONS = frozenset({"overloaded", "rate_limit", "server_error"})


def classify_agent_failure(exit_code: int, stdout: str, stderr: str) -> str:
    """Classify why an agent produced no findings.

    Returns one of: overloaded | rate_limit | server_error | parse_error | other.
    The claude CLI surfaces API errors as text on stdout (e.g.
    "API Error: 529 Overloaded ...") with a non-zero exit and empty stderr, so we
    inspect both streams — the old code recorded a useless "Non-zero exit code".
    """
    blob = f"{stdout}\n{stderr}".lower()
    if "overloaded" in blob or "529" in blob:
        return "overloaded"
    if "rate limit" in blob or "rate_limit" in blob or "429" in blob:
        return "rate_limit"
    if (
        "internal server error" in blob
        or "service unavailable" in blob
        or "api error: 500" in blob
        or "api error: 502" in blob
        or "api error: 503" in blob
    ):
        return "server_error"
    if exit_code == 0:
        return "parse_error"  # clean exit, output just didn't parse — not retryable
    return "other"


def _retry_delay(attempt: int, base_delay: float, max_delay: float, rng: random.Random) -> float:
    """Full-jitter exponential backoff: uniform(0, min(cap, base * 2**attempt)).

    Full jitter (not fixed backoff) is essential — when all 13 agents 529 at
    once, lockstep retries just re-trigger the overload; jitter desynchronizes
    them while concurrency stays at 13.
    """
    cap = min(max_delay, base_delay * (2 ** attempt))
    return rng.uniform(0, cap)


def _run_agent_attempt(
    agent_name: str,
    cmd: list[str],
    env: dict,
    timeout: int,
    start: float,
) -> AgentResult:
    """Run one claude CLI subprocess attempt and classify the outcome."""
    result = AgentResult(agent_name=agent_name)
    try:
        # Popen with its own process group so we kill the whole tree on timeout
        # (subprocess.run timeout only kills the direct child on macOS, orphaning
        # subagents that keep consuming the subscription).
        popen = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(PROJECT_ROOT),
            env=env,
            start_new_session=True,
        )
        try:
            stdout, stderr = popen.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Agent {agent_name} timed out after {timeout}s, killing process group"
            )
            kill_process_group(popen)
            popen.wait()
            result.killed_by_timeout = True
            result.classification = "timeout"
            result.error = f"Timed out after {timeout}s"
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result

        result.exit_code = popen.returncode
        result.raw_output = stdout
        result.duration_ms = int((time.monotonic() - start) * 1000)

        findings = _parse_findings(stdout, agent_name) if stdout and stdout.strip() else []
        if findings:
            # Success even with a non-zero exit (e.g. a post-output hook failed)
            # — we still got usable findings.
            result.findings = findings
            result.classification = "success"
            result.error = None
            return result

        # No findings — classify the failure from exit code + output streams.
        cls = classify_agent_failure(popen.returncode, stdout or "", stderr or "")
        result.classification = cls
        if cls == "parse_error":
            result.error = None  # clean exit, just unparseable — not an error per se
        else:
            preview = (stdout or stderr or "").strip()[:500]
            result.error = preview or f"{cls} (exit {popen.returncode})"
        return result

    except Exception as e:
        result.error = str(e)
        result.classification = "other"
        result.duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"Agent {agent_name} failed: {e}")
        return result


def run_single_agent(
    agent_name: str,
    prompt: str,
    task_type: str = "research_agent",
    *,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    _sleep=time.sleep,
    _rng: random.Random | None = None,
) -> AgentResult:
    """Run a single claude -p call for one agent, retrying transient API errors.

    Transient failures (529 overloaded, 429 rate limit, 5xx) are retried up to
    `max_attempts` with full-jitter exponential backoff. Non-transient outcomes
    (success, parse_error, timeout, other) return immediately. Every call goes
    through the claude CLI — i.e. Tayler's Anthropic subscription, never the paid
    API. `_sleep` / `_rng` are injection points for tests.
    """
    if _dry_run_enabled():
        finding = _dry_run_finding(agent_name)
        payload = {"findings": [finding]}
        logger.info("DRY RUN: skipping Claude research agent %s", agent_name)
        return AgentResult(
            agent_name=agent_name,
            findings=[finding],
            raw_output=json.dumps(payload),
            exit_code=0,
            duration_ms=0,
            error=None,
            classification="success",
        )

    rng = _rng if _rng is not None else random.Random()
    model = router.get_model(task_type)
    max_turns = router.get_max_turns(task_type)
    timeout = router.get_timeout(task_type)

    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--max-turns", str(max_turns),
        "--output-format", "text",
    ]
    for tool in AGENT_ALLOWED_TOOLS:
        cmd.extend(["--allowedTools", tool])
    # Belt and suspenders: deny the dangerous tools explicitly too —
    # allowed-tools alone is not reliably enforced in every harness path.
    cmd.extend(["--disallowedTools", "Skill Bash Agent Write Edit"])

    logger.info(
        f"run_single_agent START: agent={agent_name}, model={model}, "
        f"prompt_size={len(prompt)} chars, max_turns={max_turns}, "
        f"timeout={timeout}s, max_attempts={max_attempts}"
    )
    start = time.monotonic()
    # Pass agent identity to SessionEnd hook for transcript capture
    env = _agent_env(agent_name)

    result = AgentResult(agent_name=agent_name)
    for attempt in range(max_attempts):
        result = _run_agent_attempt(agent_name, cmd, env, timeout, start)

        if result.classification not in _TRANSIENT_CLASSIFICATIONS:
            if result.classification not in ("success", "parse_error"):
                logger.warning(
                    f"Agent {agent_name} failed: classification={result.classification}, "
                    f"exit={result.exit_code}, duration={result.duration_ms}ms, "
                    f"error_preview='{(result.error or '')[:200]}'"
                )
            return result

        if attempt < max_attempts - 1:
            delay = _retry_delay(attempt, base_delay, max_delay, rng)
            logger.warning(
                f"Agent {agent_name} transient failure ({result.classification}); "
                f"retry {attempt + 1}/{max_attempts - 1} in {delay:.1f}s"
            )
            _sleep(delay)
        else:
            logger.warning(
                f"Agent {agent_name} transient failure ({result.classification}) — "
                f"exhausted {max_attempts} attempts, giving up"
            )

    return result


def _extract_balanced_json_blocks(text: str) -> list[str]:
    """Extract all top-level balanced { } blocks from text.

    Walks through the string character by character, tracking brace depth
    and whether we are inside a JSON string (so braces inside string
    values are ignored). Returns candidate JSON substrings.
    """
    blocks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "{":
            # Start tracking a balanced block
            start = i
            depth = 0
            in_string = False
            escape = False
            j = i
            while j < n:
                ch = text[j]
                if escape:
                    escape = False
                elif ch == "\\":
                    if in_string:
                        escape = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            blocks.append(text[start : j + 1])
                            i = j  # advance outer pointer past this block
                            break
                j += 1
        i += 1
    return blocks


def _parse_findings(output: str, agent_name: str) -> list[dict]:
    """Parse JSON findings from agent output.

    Strategy:
    1. Try direct json.loads on the full (stripped) output.
    2. Extract all top-level balanced { } blocks, try json.loads on each,
       and return findings from the first block that has a "findings" key.
    3. Fall back to extracting balanced [ ] blocks for bare arrays.
    4. Log a WARNING with the first 200 chars if nothing parses.
    """
    # 1. Try direct JSON parse
    try:
        data = json.loads(output.strip())
        if isinstance(data, dict) and "findings" in data:
            return data["findings"]
    except json.JSONDecodeError:
        pass

    # 2. Balanced-brace extraction: find all top-level { } blocks, try each
    for block in _extract_balanced_json_blocks(output):
        try:
            data = json.loads(block)
            if isinstance(data, dict) and "findings" in data:
                return data["findings"]
        except json.JSONDecodeError:
            continue

    # 3. Fall back to balanced [ ] array extraction
    # Walk through looking for top-level [ ] balanced blocks
    i = 0
    n = len(output)
    while i < n:
        if output[i] == "[":
            start = i
            depth = 0
            in_string = False
            escape = False
            j = i
            while j < n:
                ch = output[j]
                if escape:
                    escape = False
                elif ch == "\\":
                    if in_string:
                        escape = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch == "[":
                        depth += 1
                    elif ch == "]":
                        depth -= 1
                        if depth == 0:
                            candidate = output[start : j + 1]
                            try:
                                items = json.loads(candidate)
                                if (
                                    isinstance(items, list)
                                    and items
                                    and isinstance(items[0], dict)
                                ):
                                    return items
                            except json.JSONDecodeError:
                                pass
                            i = j
                            break
                j += 1
        i += 1

    logger.warning(
        f"Could not parse findings from {agent_name} output "
        f"({len(output)} chars): {output[:200]!r}"
    )
    return []


def _finding_quality_score(finding: dict) -> float:
    """Score a finding for dedup tiebreaking: higher = better quality."""
    summary_len = len(finding.get("summary", ""))
    importance_weight = {"high": 3, "medium": 2, "low": 1}.get(
        finding.get("importance", "medium"), 2
    )
    url_bonus = 1.0 if finding.get("source_url") else 0.5
    return summary_len * importance_weight * url_bonus


def dedup_cross_agent_findings(
    agent_results: list[AgentResult],
    threshold: float = 0.85,
) -> tuple[list[AgentResult], dict]:
    """Remove near-duplicate findings across different agents.

    Embeds all finding summaries, computes pairwise cosine similarity via
    matrix multiplication, and for each duplicate pair keeps the higher-quality
    finding.

    Returns (modified agent_results, summary dict).
    """
    # Collect all (result_idx, finding_idx, finding) triples
    all_items: list[tuple[int, int, dict]] = []
    for ri, result in enumerate(agent_results):
        for fi, finding in enumerate(result.findings):
            all_items.append((ri, fi, finding))

    total = len(all_items)
    if total == 0:
        return agent_results, {"total": 0, "removed": 0, "kept": 0}

    if total == 1:
        return agent_results, {"total": 1, "removed": 0, "kept": 1}

    # Batch-embed all finding texts
    texts = [
        f"{item[2].get('title', '')}. {item[2].get('summary', '')}"
        for item in all_items
    ]
    embeddings = embed_texts(texts)

    # Build matrix and compute pairwise similarities
    import numpy as np
    matrix = np.array(embeddings, dtype=np.float32)
    # Normalize rows (defensive — bge-small is already normalized)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms
    sim_matrix = matrix @ matrix.T

    # Find duplicate pairs above threshold (only cross-agent, upper triangle)
    remove_set: set[int] = set()
    for i in range(total):
        if i in remove_set:
            continue
        for j in range(i + 1, total):
            if j in remove_set:
                continue
            # Only dedup across different agents
            if agent_results[all_items[i][0]].agent_name == agent_results[all_items[j][0]].agent_name:
                continue
            if sim_matrix[i, j] >= threshold:
                score_i = _finding_quality_score(all_items[i][2])
                score_j = _finding_quality_score(all_items[j][2])
                if score_i >= score_j:
                    remove_set.add(j)
                    # Tag the kept finding
                    all_items[i][2]["cross_agent_dedup"] = True
                    all_items[i][2]["dedup_kept_from"] = agent_results[all_items[j][0]].agent_name
                else:
                    remove_set.add(i)
                    all_items[j][2]["cross_agent_dedup"] = True
                    all_items[j][2]["dedup_kept_from"] = agent_results[all_items[i][0]].agent_name
                    break  # i is removed, stop comparing it

    # Rebuild findings lists, excluding removed indices
    removed_by_result: dict[int, set[int]] = {}
    for idx in remove_set:
        ri, fi, _ = all_items[idx]
        removed_by_result.setdefault(ri, set()).add(fi)

    for ri, result in enumerate(agent_results):
        if ri in removed_by_result:
            result.findings = [
                f for fi, f in enumerate(result.findings)
                if fi not in removed_by_result[ri]
            ]

    removed = len(remove_set)
    logger.info(f"Cross-agent dedup: removed {removed} duplicates from {total} total findings")

    return agent_results, {
        "total": total,
        "removed": removed,
        "kept": total - removed,
    }


def dispatch_research_agents(
    user_id: str,
    date_str: str,
    context_fn,
    trends: list[dict] | None = None,
    max_workers: int = 6,
    vertical: str = "ai-tech",
    preflight_data: dict | None = None,
) -> list[AgentResult]:
    """Dispatch all research agents in parallel via concurrent.futures.

    Args:
        user_id: The user running the pipeline.
        date_str: Today's date (YYYY-MM-DD).
        context_fn: Callable(db, agent_name, date_str) -> str that generates context.
        trends: Trending topics from Phase 2.
        max_workers: Max parallel agents.
        vertical: Vertical config to use.

    Returns:
        List of AgentResult, one per agent.
    """
    agents, agents_dir = get_agent_list(user_id, vertical)
    soul_path = PROJECT_ROOT / "verticals" / vertical / "SOUL.md"

    logger.info(f"Dispatching {len(agents)} research agents (max {max_workers} parallel)")

    results: list[AgentResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for agent_name in agents:
            skill_path = get_agent_skill_path(agent_name, user_id, vertical)
            if not skill_path.exists():
                logger.warning(f"Skill file not found for {agent_name}: {skill_path}")
                continue

            # Build context for this agent
            context = context_fn(agent_name, date_str)

            # Get preflight items assigned to this agent
            agent_preflight = None
            agent_covered = None
            if preflight_data and preflight_data.get("assignments"):
                agent_preflight = preflight_data["assignments"].get(agent_name, [])
                agent_covered = preflight_data.get("already_covered", [])

            identity_dir = PROJECT_ROOT / "data" / user_id / "mindpattern"

            prompt = build_agent_prompt(
                agent_name=agent_name,
                user_id=user_id,
                date_str=date_str,
                soul_path=soul_path,
                agent_skill_path=skill_path,
                context=context,
                trends=trends,
                preflight_items=agent_preflight,
                already_covered=agent_covered,
                identity_dir=identity_dir,
            )

            future = executor.submit(run_single_agent, agent_name, prompt)
            futures[future] = agent_name

        for future in as_completed(futures):
            agent_name = futures[future]
            try:
                result = future.result()
                results.append(result)
                findings_count = len(result.findings)
                logger.info(
                    f"Agent {agent_name}: {findings_count} findings, "
                    f"{result.duration_ms}ms"
                    + (f" (ERROR: {result.error})" if result.error else "")
                )
            except Exception as e:
                logger.error(f"Agent {agent_name} future failed: {e}")
                results.append(AgentResult(
                    agent_name=agent_name,
                    error=str(e),
                ))

    total_findings = sum(len(r.findings) for r in results)
    successful = sum(1 for r in results if not r.error)
    logger.info(
        f"Research complete: {successful}/{len(results)} agents succeeded, "
        f"{total_findings} total findings"
    )

    return results


def run_agent_with_files(
    system_prompt_file: str,
    prompt: str,
    output_file: str,
    allowed_tools: list[str] | None = None,
    task_type: str = "eic",
) -> dict | None:
    """Run a claude -p call that writes its output to a file.

    Unlike run_claude_prompt() which returns stdout text, this function
    expects the agent to write structured output (JSON or markdown) to
    output_file. Returns parsed dict or None on failure.
    """
    if allowed_tools is None:
        allowed_tools = ["Read", "Write", "Bash", "Glob", "Grep"]

    model = router.get_model(task_type)
    max_turns = router.get_max_turns(task_type)
    timeout = router.get_timeout(task_type)

    output_path = Path(output_file)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Delete stale output file if it exists
    if output_path.exists():
        output_path.unlink()

    if _dry_run_enabled():
        logger.info("DRY RUN: skipping Claude file agent %s", task_type)
        payload = _dry_run_file_payload(task_type)
        if output_path.suffix == ".md":
            text = f"# Dry Run\n\nTask type: {task_type}\n"
            output_path.write_text(text)
            return {"text": text.strip()}
        output_path.write_text(json.dumps(payload))
        return payload

    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--max-turns", str(max_turns),
        "--output-format", "text",
        "--append-system-prompt-file", system_prompt_file,
    ]
    for tool in allowed_tools:
        cmd.extend(["--allowedTools", tool])

    # Prevent subagent dispatch — agents must do their own work
    cmd.extend(["--disallowedTools", "Agent"])

    # Pass agent identity to SessionEnd hook for transcript capture
    env = _agent_env(task_type)

    proc = None
    try:
        # Use Popen with process group so we can kill the entire tree on timeout.
        # subprocess.run(timeout=) doesn't kill grandchild processes on macOS,
        # causing the bot to hang when claude spawns subagents.
        popen = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(PROJECT_ROOT),
            env=env,
            start_new_session=True,
        )
        try:
            stdout, stderr = popen.communicate(timeout=timeout)
            proc = subprocess.CompletedProcess(
                cmd, popen.returncode, stdout, stderr,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"Agent {task_type} timed out after {timeout}s, killing process group")
            kill_process_group(popen)
            popen.wait()
            proc = None
    except Exception as e:
        logger.error(f"Agent {task_type} failed to start: {e}")
        proc = None

    # Write debug log
    SOCIAL_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    debug_log_path = SOCIAL_DRAFTS_DIR / f"{task_type}-debug.log"
    exit_code = proc.returncode if proc else -1
    stdout = proc.stdout if proc else ""
    stderr = proc.stderr if proc else ""
    debug_log_path.write_text(
        f"exit_code: {exit_code}\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n"
    )

    # Read and parse output file
    if not output_path.exists():
        return None

    content = output_path.read_text().strip()
    if not content:
        return None

    if output_path.suffix == ".md":
        return {"text": content}

    if output_path.suffix == ".json":
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from {output_file}")
            return None

    # Unknown extension — try JSON, fall back to text dict
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"text": content}


def run_claude_prompt(
    prompt: str,
    task_type: str,
    *,
    system_prompt_file: str | None = None,
    allowed_tools: list[str] | None = None,
) -> tuple[str, int]:
    """Run a single claude -p call for non-agent tasks (synthesis, trends, etc.).

    For large prompts (>100K chars), writes to a temp file and pipes via stdin
    to avoid OS argument length limits.

    Returns (output_text, exit_code).
    """
    if _dry_run_enabled():
        logger.info("DRY RUN: skipping Claude prompt task_type=%s", task_type)
        return _dry_run_prompt_output(task_type), 0

    model = router.get_model(task_type)
    max_turns = router.get_max_turns(task_type)
    timeout = router.get_timeout(task_type)

    # For large prompts, use stdin pipe instead of -p argument
    use_stdin = len(prompt) > 100_000

    if use_stdin:
        cmd = [
            "claude", "-p", "-",
            "--model", model,
            "--max-turns", str(max_turns),
            "--output-format", "text",
        ]
    else:
        cmd = [
            "claude", "-p", prompt,
            "--model", model,
            "--max-turns", str(max_turns),
            "--output-format", "text",
        ]

    if system_prompt_file:
        cmd.extend(["--append-system-prompt-file", system_prompt_file])

    tools = allowed_tools if allowed_tools is not None else ["Read", "Glob", "Grep"]
    for tool in tools:
        cmd.extend(["--allowedTools", tool])

    # Prevent subagent dispatch and file writing — agents must return output
    # via stdout, not write to files. Write/Edit would let the agent put the
    # newsletter in a file instead of returning it.
    cmd.extend(["--disallowedTools", "Agent,Write,Edit,NotebookEdit,Skill"])

    # Pass agent identity to SessionEnd hook for transcript capture
    env = _agent_env(task_type)

    logger.info(
        f"run_claude_prompt START: task_type={task_type}, model={model}, "
        f"prompt_size={len(prompt)} chars, max_turns={max_turns}, timeout={timeout}s"
        + (f", system_prompt_file={system_prompt_file}" if system_prompt_file else "")
        + (f", stdin_mode=True" if use_stdin else "")
    )
    call_start = time.monotonic()

    result = run_claude_process(
        cmd,
        input_text=prompt if use_stdin else None,
        timeout=timeout,
        cwd=PROJECT_ROOT,
        env=env,
    )
    call_duration = time.monotonic() - call_start
    if result.timed_out:
        logger.error(
            f"run_claude_prompt TIMEOUT: task_type={task_type}, "
            f"timeout={timeout}s, duration={call_duration:.1f}s"
        )
        return "", 1
    if result.error:
        logger.error(
            f"run_claude_prompt ERROR: task_type={task_type}, "
            f"error={result.error}, duration={call_duration:.1f}s"
        )
        return "", 1

    logger.info(
        f"run_claude_prompt END: task_type={task_type}, "
        f"exit_code={result.returncode}, output_len={len(result.stdout)}, "
        f"duration={call_duration:.1f}s"
    )
    return result.stdout, result.returncode
