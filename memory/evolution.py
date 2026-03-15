"""Agent evolution: spawn, retire, merge, evaluate performance.

All functions take a `db` (sqlite3.Connection) parameter and/or filesystem paths
and return data structures. No argparse, no print, no CLI.

FIX from v2: Removed command injection vulnerability in _log_evolution_to_traces.
v2 used f-strings with user input in subprocess.run(..., [python, "-c", f"..."]).
v3 uses in-process db calls instead of shelling out.
"""

import hashlib
import json
import re
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from .embeddings import cosine_similarity, deserialize_f32


# ── Preference decay (shared with feedback module) ──────────────────────


def _apply_preference_decay(weight: float, updated_at: str | None) -> float:
    """Apply temporal decay to a preference weight.

    0.95^days -- 49% at 14 days, 21% at 30 days.
    """
    if not updated_at:
        return weight
    try:
        updated = datetime.strptime(updated_at[:10], "%Y-%m-%d")
        days = (datetime.now() - updated).days
        decay = 0.95 ** days
        return weight * decay
    except (ValueError, TypeError):
        return weight


# ── Candidate identification ────────────────────────────────────────────


def get_candidates(db: sqlite3.Connection) -> dict:
    """Identify spawn/retire candidates from preference weights with decay.

    Returns {spawn: [...], retire: [...]}.
    """
    rows = db.execute(
        "SELECT email, topic, weight, updated_at FROM user_preferences ORDER BY weight DESC"
    ).fetchall()

    spawn = []
    retire = []
    for r in rows:
        eff = _apply_preference_decay(r["weight"], r["updated_at"])
        entry = {
            "topic": r["topic"],
            "email": r["email"],
            "raw_weight": r["weight"],
            "effective_weight": round(eff, 3),
        }
        if eff >= 2.5:
            spawn.append(entry)
        elif eff <= -2.0:
            retire.append(entry)

    return {"spawn": spawn, "retire": retire}


# ── Performance checking ────────────────────────────────────────────────


def check_agent_performance(
    db: sqlite3.Connection,
    agent: str,
    runs: int = 5,
) -> dict:
    """Check an agent's recent performance for retirement eligibility.

    Uses run_log table (which captures zero-output runs) as primary source.
    Falls back to findings table for backwards compatibility if run_log has no data.

    Returns {agent, runs_checked, consecutive_zero_high_value, should_retire}.
    """
    # Try run_log first -- it tracks all runs including zero-output ones
    run_log_dates = db.execute(
        "SELECT run_date, findings_count FROM run_log WHERE agent = ? ORDER BY run_date DESC LIMIT ?",
        (agent, runs),
    ).fetchall()

    if run_log_dates:
        consecutive_zero = 0
        for row in run_log_dates:
            if row["findings_count"] == 0:
                consecutive_zero += 1
            else:
                # Has findings; check if any are high-value
                high_count = db.execute(
                    "SELECT COUNT(*) as c FROM findings WHERE agent = ? AND run_date = ? AND importance = 'high'",
                    (agent, row["run_date"]),
                ).fetchone()["c"]
                if high_count == 0:
                    consecutive_zero += 1
                else:
                    break

        return {
            "agent": agent,
            "runs_checked": len(run_log_dates),
            "consecutive_zero_high_value": consecutive_zero,
            "should_retire": consecutive_zero >= runs,
        }

    # Fallback: use findings table (pre-run_log data)
    dates = db.execute(
        "SELECT DISTINCT run_date FROM findings WHERE agent = ? ORDER BY run_date DESC LIMIT ?",
        (agent, runs),
    ).fetchall()

    if not dates:
        # No findings and no run_log -- agent may be newly spawned, don't flag
        return {
            "agent": agent,
            "runs_checked": 0,
            "consecutive_zero_high_value": 0,
            "should_retire": False,
        }

    consecutive_zero = 0
    for row in dates:
        high_count = db.execute(
            "SELECT COUNT(*) as c FROM findings WHERE agent = ? AND run_date = ? AND importance = 'high'",
            (agent, row["run_date"]),
        ).fetchone()["c"]
        if high_count == 0:
            consecutive_zero += 1
        else:
            break  # Found a run with high-value findings, stop counting

    return {
        "agent": agent,
        "runs_checked": len(dates),
        "consecutive_zero_high_value": consecutive_zero,
        "should_retire": consecutive_zero >= runs,
    }


# ── Overlap detection ───────────────────────────────────────────────────


def compute_overlap(
    db: sqlite3.Connection,
    agent1: str,
    agent2: str,
    days: int = 14,
) -> dict:
    """Compute finding overlap between two agents using embedding similarity.

    Threshold: 0.85 (same as findings dedup).

    Returns {overlap_pct, should_merge, overlapping_findings}.
    """
    threshold = 0.85
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Get embeddings for each agent
    rows1 = db.execute(
        """SELECT f.id, e.embedding FROM findings f
           JOIN findings_embeddings e ON e.finding_id = f.id
           WHERE f.agent = ? AND f.run_date >= ?""",
        (agent1, cutoff),
    ).fetchall()

    rows2 = db.execute(
        """SELECT f.id, e.embedding FROM findings f
           JOIN findings_embeddings e ON e.finding_id = f.id
           WHERE f.agent = ? AND f.run_date >= ?""",
        (agent2, cutoff),
    ).fetchall()

    if not rows1 or not rows2:
        return {
            "overlap_pct": 0.0,
            "should_merge": False,
            "overlapping_findings": 0,
        }

    # Deserialize embeddings
    vecs1 = [deserialize_f32(r["embedding"]) for r in rows1]
    vecs2 = [deserialize_f32(r["embedding"]) for r in rows2]

    # Count overlapping pairs: for each finding in smaller set,
    # check if any finding in larger set has similarity >= threshold
    smaller, larger = (vecs1, vecs2) if len(vecs1) <= len(vecs2) else (vecs2, vecs1)
    overlap_count = 0
    for v_s in smaller:
        for v_l in larger:
            sim = cosine_similarity(v_s, v_l)
            if sim >= threshold:
                overlap_count += 1
                break  # Count each finding in smaller set at most once

    overlap_pct = round(100.0 * overlap_count / len(smaller), 1)

    return {
        "overlap_pct": overlap_pct,
        "should_merge": overlap_pct > 30,
        "overlapping_findings": overlap_count,
    }


# ── Evolution logging ───────────────────────────────────────────────────


def log_evolution(
    db: sqlite3.Connection,
    run_date: str,
    action: str,
    agents: str,
    reason: str,
) -> None:
    """Log an evolution action to agent_notes with type 'evolution'.

    FIX from v2: This is an in-process db call instead of subprocess.run
    with f-string interpolation of user input (command injection risk).
    """
    now = datetime.now().isoformat()

    content = json.dumps({
        "action": action,
        "agents": agents,
        "reason": reason,
    })

    db.execute(
        """INSERT INTO agent_notes (run_date, agent, note_type, content, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (run_date, "orchestrator", "evolution", content, now),
    )
    db.commit()


# ── Status & init ───────────────────────────────────────────────────────


def get_evolution_status(overrides_dir: str | Path) -> dict:
    """Report current agent evolution state from agents.json.

    Returns {has_overrides, active_agents, retired_agents, evolved_agents, base_vertical}.
    """
    overrides_dir = Path(overrides_dir)
    agents_json = overrides_dir / "agents.json"

    if not agents_json.exists():
        return {
            "has_overrides": False,
            "active_agents": [],
            "retired_agents": [],
            "evolved_agents": {},
        }

    with open(agents_json) as f:
        data = json.load(f)

    return {
        "has_overrides": True,
        "active_agents": data.get("agents", []),
        "retired_agents": data.get("retired", []),
        "evolved_agents": data.get("evolved_agents", {}),
        "base_vertical": data.get("base_vertical", ""),
    }


def init_evolution(
    overrides_dir: str | Path,
    vertical_config_path: str | Path,
) -> dict:
    """Initialize agent-overrides directory and agents.json from vertical config.

    Returns {initialized, agents_count}.
    """
    overrides_dir = Path(overrides_dir)
    overrides_dir.mkdir(parents=True, exist_ok=True)

    with open(vertical_config_path) as f:
        vert = json.load(f)

    agents_json = overrides_dir / "agents.json"
    data = {
        "agents": vert.get("agents", []),
        "base_vertical": vert.get("id", ""),
        "retired": [],
        "evolved_agents": {},
    }

    with open(agents_json, "w") as f:
        json.dump(data, f, indent=2)

    return {"initialized": True, "agents_count": len(data["agents"])}


# ── Markdown section extraction ─────────────────────────────────────────


def _extract_section(content: str, heading: str) -> str:
    """Extract a markdown section by heading name, returning its body text."""
    in_section = False
    lines = []
    for line in content.split("\n"):
        if line.strip().startswith(f"## {heading}"):
            in_section = True
            continue
        elif line.strip().startswith("## ") and in_section:
            break
        elif in_section:
            lines.append(line)
    return "\n".join(lines).strip()


# ── Spawn ───────────────────────────────────────────────────────────────


def spawn_agent(
    db: sqlite3.Connection,
    overrides_dir: str | Path,
    topic: str,
    parent_agent: str,
    parent_agent_file: str | Path | None = None,
    date: str | None = None,
) -> dict:
    """Spawn a new focused agent based on a parent agent.

    Sanitizes agent name, validates path traversal, generates skill file
    from parent template.

    Returns {spawned, agent_name, skill_file, parent} on success,
            {spawned: False, reason: ...} on failure.
    """
    overrides_dir = Path(overrides_dir)
    agents_json = overrides_dir / "agents.json"

    if not agents_json.exists():
        return {"spawned": False, "reason": "agents.json not found. Run evolution init first."}

    with open(agents_json) as f:
        data = json.load(f)

    # Sanitize agent name: only allow lowercase alphanumeric and hyphens
    safe_name = re.sub(r'[^a-z0-9-]', '', topic.lower().replace(" ", "-")).strip("-")
    if not safe_name:
        return {"spawned": False, "reason": "Topic produces empty agent name after sanitization"}
    new_agent_name = safe_name + "-researcher"

    # Validate the resulting file path stays within overrides_dir
    skill_file = overrides_dir / f"{new_agent_name}.md"
    if not skill_file.resolve().is_relative_to(overrides_dir.resolve()):
        return {"spawned": False, "reason": "Path traversal detected in agent name"}

    if new_agent_name in data.get("agents", []):
        return {"spawned": False, "reason": f"Agent {new_agent_name} already exists"}

    # Read parent agent skill file to use as template
    parent_content = ""
    if parent_agent_file and Path(parent_agent_file).exists():
        with open(parent_agent_file) as f:
            parent_content = f.read()

    # Extract Priority Sources and Output Format from parent if available
    parent_priority_sources = _extract_section(parent_content, "Priority Sources") if parent_content else ""
    parent_output_format = _extract_section(parent_content, "Output Format") if parent_content else ""

    # Generate focused skill file
    topic_title = topic.replace("-", " ").title()

    # Use parent sections if available, otherwise use defaults
    if parent_priority_sources:
        priority_sources_body = parent_priority_sources
    else:
        priority_sources_body = (
            f"Search broadly for {topic_title} content across:\n"
            f"- News sites (TechCrunch, The Verge, Ars Technica)\n"
            f"- Technical blogs and company announcements\n"
            f"- Social media discussions (Twitter/X, Reddit, HN)\n"
            f"- Academic papers (arXiv, Google Scholar)"
        )

    if parent_output_format:
        output_format_body = parent_output_format
    else:
        output_format_body = (
            f"For each finding, include:\n"
            f"- **Title**: Clear, descriptive headline\n"
            f"- **Source**: URL and publication name\n"
            f"- **Category**: {topic_title}\n"
            f"- **Importance**: high/medium/low\n"
            f"- **Summary**: 2-3 sentences explaining what happened and why it matters"
        )

    skill_content = f"""# Agent: {topic_title} Researcher

## Learnings

Before searching, read your past learnings for patterns to apply and mistakes to avoid:
- `data/{{user}}/learnings.md` — distilled insights from previous runs

You are a specialized researcher focused on **{topic_title}**. This agent was spawned from {parent_agent} due to high user interest in this topic.

## Focus Areas

- Latest developments in {topic_title}
- Key players and organizations in {topic_title}
- Practical applications and tutorials for {topic_title}
- Community discussions and opinions about {topic_title}
- Research papers and breakthroughs in {topic_title}

## Priority Sources

{priority_sources_body}

## Output Format

{output_format_body}
"""

    with open(skill_file, "w") as f:
        f.write(skill_content)

    # Update agents.json
    spawn_date = date or datetime.now().strftime("%Y-%m-%d")

    data.setdefault("agents", []).append(new_agent_name)
    data.setdefault("evolved_agents", {})[new_agent_name] = {
        "spawned_from": parent_agent,
        "reason": f"User preference weight for {topic}",
        "spawned_date": spawn_date,
    }

    with open(agents_json, "w") as f:
        json.dump(data, f, indent=2)

    # Log evolution in-process (v2 FIX: no more subprocess.run with f-strings)
    log_evolution(db, spawn_date, "spawn", new_agent_name,
                  f"Spawned from {parent_agent} for topic {topic}")

    return {
        "spawned": True,
        "agent_name": new_agent_name,
        "skill_file": str(skill_file),
        "parent": parent_agent,
    }


# ── Retire ──────────────────────────────────────────────────────────────


def retire_agent(overrides_dir: str | Path, agent: str) -> dict:
    """Retire an agent by moving it from agents to retired list.

    Returns {retired, agent} on success, {retired: False, reason: ...} on failure.
    """
    overrides_dir = Path(overrides_dir)
    agents_json = overrides_dir / "agents.json"

    if not agents_json.exists():
        return {"retired": False, "reason": "agents.json not found"}

    with open(agents_json) as f:
        data = json.load(f)

    agents = data.get("agents", [])
    if agent not in agents:
        return {"retired": False, "reason": f"Agent {agent} not in active list"}

    agents.remove(agent)
    data.setdefault("retired", []).append(agent)

    with open(agents_json, "w") as f:
        json.dump(data, f, indent=2)

    return {"retired": True, "agent": agent}


# ── Merge ───────────────────────────────────────────────────────────────


def merge_agents(
    overrides_dir: str | Path,
    survivor: str,
    retiring: str,
    vertical_agents_dir: str | Path | None = None,
) -> dict:
    """Merge two agents: expand survivor's scope, retire the other.

    Returns {merged, survivor, retired} on success,
            {merged: False, reason: ...} on failure.
    """
    overrides_dir = Path(overrides_dir)
    agents_json = overrides_dir / "agents.json"

    if not agents_json.exists():
        return {"merged": False, "reason": "agents.json not found"}

    with open(agents_json) as f:
        data = json.load(f)

    agents = data.get("agents", [])
    if survivor not in agents:
        return {"merged": False, "reason": f"Survivor agent {survivor} not in active list"}
    if retiring not in agents:
        return {"merged": False, "reason": f"Retiring agent {retiring} not in active list"}

    # Read retiring agent's skill file to extract focus areas
    retiring_file = overrides_dir / f"{retiring}.md"
    retiring_focus = ""
    if retiring_file.exists():
        with open(retiring_file) as f:
            content = f.read()
        retiring_focus = _extract_section(content, "Focus Areas")

    # Update survivor's skill file
    survivor_file = overrides_dir / f"{survivor}.md"
    if not survivor_file.exists():
        # Copy base vertical skill file to agent-overrides/ first
        if vertical_agents_dir:
            base_dir = Path(vertical_agents_dir)
            if (base_dir / f"{survivor}.md").exists():
                shutil.copy2(str(base_dir / f"{survivor}.md"), str(survivor_file))

    if survivor_file.exists():
        with open(survivor_file) as f:
            survivor_content = f.read()

        # Append merged focus areas
        merge_section = f"\n\n## Merged Coverage (from {retiring})\n\n{retiring_focus}\n"
        survivor_content += merge_section

        with open(survivor_file, "w") as f:
            f.write(survivor_content)

    # Retire the other agent
    if retiring in agents:
        agents.remove(retiring)
    data.setdefault("retired", []).append(retiring)

    # Record merge metadata
    data.setdefault("evolved_agents", {})[survivor] = {
        **data.get("evolved_agents", {}).get(survivor, {}),
        "merged_with": retiring,
        "merged_date": datetime.now().strftime("%Y-%m-%d"),
    }

    with open(agents_json, "w") as f:
        json.dump(data, f, indent=2)

    return {
        "merged": True,
        "survivor": survivor,
        "retired": retiring,
    }
