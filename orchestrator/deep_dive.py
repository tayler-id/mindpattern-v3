"""Deep-dive research on the Top stories, before the newsletter is written.

One agent per Top story (config task "story_deep_dive", Sonnet 5.5) looks for
the primary source, corroboration, the numbers, a quote, and the strongest
counterpoint, and stores each item with `mp evidence add`. A lead story's agent
gets its angle and every finding in it, and tests the angle. The writer gets
the stored items as an evidence pack per story. Everything here fails open: a
story without a pack is written from its findings, as before.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Callable

from core import findings_store
from core.claude_cli import run_claude_process
from core.model_cli import ToolPolicy, run_task_process

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT = PROJECT_ROOT / "agents" / "story-deep-dive.md"
TASK = "story_deep_dive"
TOOLS = ToolPolicy(allowed=("WebSearch", "WebFetch", "Bash(mp *)", "Bash(bin/mp *)"),
                   disallowed=("Agent", "Write", "Edit", "NotebookEdit", "Skill"))
MAX_PARALLEL = 3
_WORD = re.compile(r"[a-z0-9]+")


@dataclass
class DeepDive:
    story_id: str
    title: str
    finding: dict[str, Any] | None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    outcome: str = "not run"
    angle: str = ""
    members: list[dict[str, Any]] = field(default_factory=list)


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower().replace("[security research]", "")))


def story_id(title: str) -> str:
    return "-".join(_WORD.findall(title.lower()))[:60] or "story"


def picks(pass1_output: str) -> list[dict[str, str]]:
    """The selector's picks: [{"story_title", "agent", ...}], or [] if unreadable."""
    match = re.search(r"\[.*\]", pass1_output.strip(), re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict) and d.get("story_title")] if isinstance(data, list) else []


def stories_from_selection(pass1_output: str, findings: list[dict[str, Any]], limit: int) -> list[DeepDive]:
    """Match each pick to the finding it came from (same agent first, then any)."""
    stories = []
    for pick in picks(pass1_output)[:limit]:
        wanted = _words(pick["story_title"])
        candidates = sorted(
            findings,
            key=lambda f: (f.get("agent") == pick.get("agent"),
                           len(wanted & _words(f.get("title", ""))) / max(len(wanted | _words(f.get("title", ""))), 1)),
            reverse=True,
        )
        best = candidates[0] if candidates else None
        overlap = len(wanted & _words(best.get("title", ""))) / max(len(wanted), 1) if best else 0
        stories.append(DeepDive(story_id(pick["story_title"]), pick["story_title"],
                                best if overlap >= 0.5 else None))
    return stories


def build_prompt(story: DeepDive) -> str:
    lines = [f"Story id: {story.story_id}", f"Story: {story.title}"]
    if story.angle:
        lines += [f"Angle: {story.angle}", "Built from these findings:"]
        lines += [f"- {m['title']} ({m['source_name']}, {m['source_url']}). {m['summary']}" for m in story.members]
    if story.finding:
        for key in ("summary", "source_url", "source_name"):
            if story.finding.get(key):
                lines.append(f"{key.replace('_', ' ').capitalize()}: {story.finding[key]}")
    lines.append(f"\nFind the evidence behind this story and store each item with "
                 f"`mp evidence add --story {story.story_id}`.")
    return "\n".join(lines)


def run_deep_dives(stories: list[DeepDive], *, evidence_dir: Path, env: dict[str, str] | None = None,
                   runner: Callable[..., Any] = run_claude_process) -> list[DeepDive]:
    """Run one agent per story, at most MAX_PARALLEL at a time, and read back what each stored."""
    base_env = {**(env or {}), "PATH": f"{PROJECT_ROOT / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"}
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def one(story: DeepDive) -> DeepDive:
        store = evidence_dir / f"{story.story_id}.evidence.jsonl"
        try:
            process = run_task_process(
                TASK, prompt=build_prompt(story), system_prompt_file=SYSTEM_PROMPT, tools=TOOLS,
                unit=story.story_id, cwd=PROJECT_ROOT, runner=runner,
                env={**base_env, "MP_EVIDENCE_FILE": str(store), "MINDPATTERN_AGENT": f"deep-dive-{story.story_id}"},
            )
            story.outcome = "success" if process.returncode == 0 else (
                "timeout" if process.timed_out else f"exit {process.returncode}")
        except Exception as exc:
            logger.warning("deep dive %s failed open: %s", story.story_id, exc)
            story.outcome = f"error: {exc}"
        story.evidence = [row for row in findings_store.read_rows(store) if row.get("story") == story.story_id]
        return story

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        return list(pool.map(one, stories))


def evidence_block(stories: list[DeepDive]) -> str:
    """The writer's evidence packs, one per story that has any."""
    packs = [s for s in stories if s.evidence]
    if not packs:
        return ""
    lines = ["## Evidence packs (deep dives on today's picks)",
             "Verified items gathered for each Top story. Prefer these sources and numbers; never add facts "
             "that neither the findings nor these packs contain.", ""]
    for story in packs:
        lines.append(f"### {story.title}")
        for item in story.evidence:
            quote = f' Quote: "{item["quote"]}"' if item.get("quote") else ""
            lines.append(f"- [{item.get('kind')}] {item.get('claim')} ({item.get('source_name')}, "
                         f"{item.get('source_url')}).{quote}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def summary(stories: list[DeepDive]) -> dict[str, Any]:
    return {"stories": len(stories), "with_evidence": sum(1 for s in stories if s.evidence),
            "items": sum(len(s.evidence) for s in stories),
            "outcomes": {s.story_id: s.outcome for s in stories}}
