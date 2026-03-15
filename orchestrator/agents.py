"""Claude CLI dispatch for research agents.

Key change from v2: instead of one monolithic claude -p call that orchestrates
everything, we make individual per-agent calls via concurrent.futures. Each agent
gets a focused prompt with its context. Python controls the orchestration.
"""

import json
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import router

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Tools each agent is allowed to use
AGENT_ALLOWED_TOOLS = [
    "Bash", "WebSearch", "WebFetch", "Read", "Glob", "Grep",
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
    claims: list[str] | None = None,
) -> str:
    """Build the prompt for a single research agent.

    Structure (IFScale: critical rules at start AND end):
    1. Critical output rules (JSON schema)
    2. SOUL identity
    3. Agent skill definition
    4. Dynamic context (date, trends, memory context, claims)
    5. Search instructions (SMTL: search ALL first, then reason)
    6. Critical output rules repeated
    """
    soul_content = soul_path.read_text() if soul_path.exists() else ""
    skill_content = agent_skill_path.read_text() if agent_skill_path.exists() else ""

    trends_section = ""
    if trends:
        topics = ", ".join(t.get("topic", "") for t in trends[:8])
        trends_section = f"\n## Today's Trending Topics\n{topics}\n"

    claims_section = ""
    if claims:
        claims_section = (
            "\n## Already Claimed Topics (DO NOT duplicate)\n"
            + "\n".join(f"- {c}" for c in claims)
            + "\n"
        )

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

{skill_content}

---

## Research Context — {date_str}
{trends_section}
{claims_section}
{context}

---

## Search Instructions (SMTL)

PHASE A: Execute ALL search queries. Collect all results. Do NOT evaluate yet.
PHASE B: Now reason over collected evidence. Score each finding.

For each finding evaluation, use max 5 words per reasoning step.
Do not explain your full reasoning — just output the finding.

---

CRITICAL REMINDER: Output ONLY the JSON object with "findings" array. No other text.
"""
    return prompt


def run_single_agent(
    agent_name: str,
    prompt: str,
    task_type: str = "research_agent",
) -> AgentResult:
    """Run a single claude -p call for one agent.

    Returns AgentResult with parsed findings or error.
    """
    model = router.get_model(task_type)
    max_turns = router.get_max_turns(task_type)
    timeout = router.get_timeout(task_type)

    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--max-turns", str(max_turns),
        "--output-format", "text",
    ]

    # Add allowed tools
    for tool in AGENT_ALLOWED_TOOLS:
        cmd.extend(["--allowedTools", tool])

    start = time.monotonic()
    result = AgentResult(agent_name=agent_name)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        result.exit_code = proc.returncode
        result.raw_output = proc.stdout
        result.duration_ms = int((time.monotonic() - start) * 1000)

        if proc.returncode != 0:
            result.error = proc.stderr[:500] if proc.stderr else "Non-zero exit code"
            logger.warning(f"Agent {agent_name} exited with code {proc.returncode}")
            return result

        # Parse JSON findings from output
        result.findings = _parse_findings(proc.stdout, agent_name)

    except subprocess.TimeoutExpired:
        result.killed_by_timeout = True
        result.error = f"Timed out after {timeout}s"
        result.duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(f"Agent {agent_name} timed out after {timeout}s")

    except Exception as e:
        result.error = str(e)
        result.duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"Agent {agent_name} failed: {e}")

    return result


def _parse_findings(output: str, agent_name: str) -> list[dict]:
    """Parse JSON findings from agent output.

    Tries to find a JSON object with a "findings" array in the output.
    Falls back to extracting the largest JSON block.
    """
    import re

    # Try direct JSON parse
    try:
        data = json.loads(output.strip())
        if isinstance(data, dict) and "findings" in data:
            return data["findings"]
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in output (agent might have prefixed text)
    json_match = re.search(r'\{[\s\S]*"findings"[\s\S]*\}', output)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if isinstance(data, dict) and "findings" in data:
                return data["findings"]
        except json.JSONDecodeError:
            pass

    # Try to find a JSON array directly
    array_match = re.search(r'\[[\s\S]*\]', output)
    if array_match:
        try:
            items = json.loads(array_match.group())
            if isinstance(items, list) and items and isinstance(items[0], dict):
                return items
        except json.JSONDecodeError:
            pass

    logger.warning(f"Could not parse findings from {agent_name} output ({len(output)} chars)")
    return []


def dispatch_research_agents(
    user_id: str,
    date_str: str,
    context_fn,
    trends: list[dict] | None = None,
    claims: list[str] | None = None,
    max_workers: int = 6,
    vertical: str = "ai-tech",
) -> list[AgentResult]:
    """Dispatch all research agents in parallel via concurrent.futures.

    Args:
        user_id: The user running the pipeline.
        date_str: Today's date (YYYY-MM-DD).
        context_fn: Callable(db, agent_name, date_str) -> str that generates context.
        trends: Trending topics from Phase 2.
        claims: Already-claimed topic hashes.
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

            prompt = build_agent_prompt(
                agent_name=agent_name,
                user_id=user_id,
                date_str=date_str,
                soul_path=soul_path,
                agent_skill_path=skill_path,
                context=context,
                trends=trends,
                claims=claims,
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


def run_claude_prompt(
    prompt: str,
    task_type: str,
    *,
    system_prompt_file: str | None = None,
    allowed_tools: list[str] | None = None,
) -> tuple[str, int]:
    """Run a single claude -p call for non-agent tasks (synthesis, trends, etc.).

    Returns (output_text, exit_code).
    """
    model = router.get_model(task_type)
    max_turns = router.get_max_turns(task_type)
    timeout = router.get_timeout(task_type)

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

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        return proc.stdout, proc.returncode
    except subprocess.TimeoutExpired:
        logger.error(f"Claude call timed out after {timeout}s for {task_type}")
        return "", 1
    except Exception as e:
        logger.error(f"Claude call failed for {task_type}: {e}")
        return "", 1
