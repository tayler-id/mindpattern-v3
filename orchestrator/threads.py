"""Lead stories: original stories built from several of today's findings that connect.

Opus 5.5 (route `thread_finder`) reads every finding of the day and proposes
lead stories. Each is an angle that three to five findings support together and
none supports alone. Code holds each to the contract and the policy: members are
real findings from today, a finding serves one lead story at most, findings a
past issue already used don't count, and each story keeps at least
`min_members` findings from at least `min_agents` agents. The strongest fill
the issue's Top slots ahead of single-finding picks. Earlier coverage of a
story's findings, found from embeddings and knowledge-graph entities, is
attached so the writer can say what today adds. Everything fails open: no lead
stories means the selector picks every Top story, as before.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
import json
import logging
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable

from orchestrator.deep_dive import DeepDive, story_id

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT = PROJECT_ROOT / "agents" / "thread-finder.md"
TASK = "thread_finder"
_TOKEN = re.compile(r"[a-z0-9][a-z0-9.+\-]*[a-z0-9+]|[a-z0-9]")


@dataclass(frozen=True)
class ThreadPolicy:
    leads: int = 5
    proposals: int = 7
    min_members: int = 3
    min_agents: int = 2
    candidates: int = 30
    window_days: int = 30
    min_earlier_days: int = 1
    similarity: float = 0.72
    max_entity_findings: int = 150


@dataclass(frozen=True)
class Episode:
    finding_id: int
    run_date: str
    agent: str
    title: str
    summary: str
    source_name: str
    source_url: str


@dataclass
class Candidate:
    """Today's findings that continue an earlier story (the earlier-coverage context)."""
    today: list[Episode]
    earlier: list[Episode]
    entities: list[str]

    @property
    def earlier_days(self) -> list[str]:
        return sorted({e.run_date for e in self.earlier})

    def score(self) -> float:
        return len(self.earlier_days) + 2 * len(self.today) + len({e.agent for e in self.today})


@dataclass
class Thread:
    """One lead story: a working title, the angle its findings support together, and those findings."""
    title: str
    angle: str
    members: list[Episode]
    strength: int
    earlier: list[Episode] = field(default_factory=list)


def load_policy(path: Path | None = None) -> ThreadPolicy:
    """The `threads` section of editorial.json. Lead stories fill at most newsletter.top_stories slots."""
    from orchestrator import editorial

    path = path or editorial.POLICY_PATH
    raw = json.loads(path.read_text()).get("threads") or {}
    defaults = ThreadPolicy()
    values = {}
    for key, low, high in (("proposals", 1, 12), ("min_members", 2, 8), ("min_agents", 1, 13),
                           ("candidates", 1, 100), ("window_days", 3, 120), ("min_earlier_days", 1, 30),
                           ("max_entity_findings", 1, 100000)):
        value = raw.get(key, getattr(defaults, key))
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise editorial.EditorialPolicyError(f"editorial.json threads.{key} must be an integer from {low} to {high}")
        values[key] = value
    similarity = raw.get("similarity", defaults.similarity)
    if isinstance(similarity, bool) or not isinstance(similarity, (int, float)) or not 0.5 <= similarity <= 0.99:
        raise editorial.EditorialPolicyError("editorial.json threads.similarity must be a number from 0.5 to 0.99")
    return ThreadPolicy(leads=editorial.load(path).top_stories, similarity=float(similarity), **values)


def today_episodes(conn: sqlite3.Connection, today: str) -> list[Episode]:
    rows = conn.execute("SELECT id, run_date, agent, title, summary, source_name, source_url FROM findings "
                        "WHERE run_date = ? ORDER BY id", (today,)).fetchall()
    return [Episode(r[0], r[1], r[2] or "", r[3] or "", r[4] or "", r[5] or "", r[6] or "") for r in rows]


def _norm(text: str) -> str:
    return " ".join(_TOKEN.findall((text or "").lower()))


def _mentions(text: str, aliases: dict[str, set[int]]) -> set[int]:
    tokens = _TOKEN.findall((text or "").lower())
    found: set[int] = set()
    for n in range(1, 5):
        for i in range(len(tokens) - n + 1):
            found |= aliases.get(" ".join(tokens[i:i + n]), set())
    return found


def find_candidates(conn: sqlite3.Connection, today: str, policy: ThreadPolicy) -> list[Candidate]:
    """Today's findings that continue earlier stories, best first. Deterministic; no model calls."""
    import numpy as np

    from memory.embeddings import deserialize_f32

    start = (date.fromisoformat(today) - timedelta(days=policy.window_days)).isoformat()
    rows = conn.execute(
        "SELECT f.id, f.run_date, f.agent, f.title, f.summary, f.source_name, f.source_url, e.embedding "
        "FROM findings f JOIN findings_embeddings e ON e.finding_id = f.id WHERE f.run_date BETWEEN ? AND ?",
        (start, today)).fetchall()
    episodes = [Episode(r[0], r[1], r[2] or "", r[3] or "", r[4] or "", r[5] or "", r[6] or "") for r in rows]
    today_idx = [i for i, e in enumerate(episodes) if e.run_date == today]
    prior_idx = [i for i, e in enumerate(episodes) if e.run_date < today]
    if not today_idx or not prior_idx:
        return []

    prior_ids = [episodes[i].finding_id for i in prior_idx]
    linked: dict[int, set[int]] = {}
    marks = ",".join("?" * len(prior_ids))
    for finding_id, entity_id in conn.execute(
            f"SELECT finding_id, subject_id FROM kg_edges WHERE finding_id IN ({marks}) "
            f"UNION SELECT finding_id, object_id FROM kg_edges WHERE finding_id IN ({marks})", prior_ids + prior_ids):
        linked.setdefault(finding_id, set()).add(entity_id)
    frequency = dict(conn.execute(
        "SELECT eid, count(*) FROM (SELECT finding_id fid, subject_id eid FROM kg_edges WHERE finding_id IS NOT NULL "
        "UNION SELECT finding_id, object_id FROM kg_edges WHERE finding_id IS NOT NULL) GROUP BY eid"))
    specific = {e for ids in linked.values() for e in ids if frequency.get(e, 0) <= policy.max_entity_findings}
    aliases: dict[str, set[int]] = {}
    names: dict[int, str] = {}
    for entity_id, name in conn.execute("SELECT id, canonical_name FROM kg_entities"):
        names[entity_id] = name
    for entity_id, alias in conn.execute(
            "SELECT entity_id, alias FROM kg_entity_aliases UNION SELECT id, canonical_name FROM kg_entities"):
        if entity_id in specific and len(alias or "") >= 3:
            aliases.setdefault(_norm(alias), set()).add(entity_id)

    vectors = np.array([deserialize_f32(r[7]) for r in rows], dtype=np.float32)
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)
    similarity = vectors[today_idx] @ vectors[prior_idx].T

    links: dict[int, list[tuple[int, set[int]]]] = {}
    for a, ti in enumerate(today_idx):
        mentioned = _mentions(f"{episodes[ti].title} {episodes[ti].summary}", aliases)
        for b in np.where(similarity[a] >= policy.similarity)[0]:
            pi = prior_idx[int(b)]
            shared = mentioned & linked.get(episodes[pi].finding_id, set())
            if shared:
                links.setdefault(ti, []).append((pi, shared))

    parent = {ti: ti for ti in links}

    def root(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # Two of today's findings join only when they continue the same earlier
    # story AND are close to each other. Joining on a shared earlier finding
    # alone chained 20 unrelated stories into one thread on 2026-10-10.
    position = {ti: a for a, ti in enumerate(today_idx)}
    today_vectors = vectors[today_idx]
    by_prior: dict[int, list[int]] = {}
    for ti, hits in links.items():
        for pi, _ in hits:
            by_prior.setdefault(pi, []).append(ti)
    for members in by_prior.values():
        for i, first in enumerate(members):
            for second in members[i + 1:]:
                close = float(today_vectors[position[first]] @ today_vectors[position[second]])
                if close >= policy.similarity:
                    parent[root(second)] = root(first)

    groups: dict[int, list[int]] = {}
    for ti in links:
        groups.setdefault(root(ti), []).append(ti)
    candidates = []
    for members in groups.values():
        earlier = {pi: shared for ti in members for pi, shared in links[ti]}
        entity_ids = set().union(*earlier.values())
        candidate = Candidate(
            today=sorted((episodes[ti] for ti in members), key=lambda e: e.finding_id),
            earlier=sorted((episodes[pi] for pi in earlier), key=lambda e: (e.run_date, e.finding_id)),
            entities=[names.get(e, "") for e in sorted(entity_ids, key=lambda e: (frequency.get(e, 0), names.get(e, "")))])
        if len(candidate.earlier_days) >= policy.min_earlier_days:
            candidates.append(candidate)
    candidates.sort(key=lambda c: (-c.score(), c.today[0].finding_id))
    return candidates[:policy.candidates]


def build_prompt(episodes: list[Episode], *, policy: ThreadPolicy, notes: dict[int, str], published: str) -> str:
    lines = [f"Propose up to {policy.proposals} lead stories. The {policy.leads} strongest that pass the rules "
             "lead today's issue.", ""]
    if published:
        lines += [published.strip(), ""]
    lines += [f"## Today's findings ({len(episodes)})",
              "Each is #id [agent] title (source), then any note, then the summary.", ""]
    for e in episodes:
        lines.append(f"#{e.finding_id} [{e.agent}] {e.title} ({e.source_name})")
        if notes.get(e.finding_id):
            lines.append(f"  {notes[e.finding_id]}")
        lines.append(f"  {e.summary}")
    return "\n".join(lines)


def find_threads(conn: sqlite3.Connection, today: str, *, policy: ThreadPolicy,
                 notes: dict[int, str] | None = None, covered: frozenset[int] | set[int] = frozenset(),
                 published: str = "", runner: Callable[..., Any] | None = None) -> list[Thread]:
    """Today's lead stories, checked against the contract and the policy, strongest first. [] on any failure.

    `notes` are per-finding lines shown to the model ("Also found by", already covered).
    `covered` holds the ids of findings a past issue already used; they never count toward a story.
    """
    episodes = today_episodes(conn, today)
    if not policy.leads or len(episodes) < policy.min_members:
        return []
    from core import contracts
    from core.claude_cli import run_claude_process
    from core.llm import extract_json
    from core.model_cli import ToolPolicy, run_task_process

    try:
        process = run_task_process(
            TASK, prompt=build_prompt(episodes, policy=policy, notes=notes or {}, published=published),
            system_prompt_file=SYSTEM_PROMPT,
            tools=ToolPolicy(allowed=(), disallowed=("Bash", "Read", "Write", "Edit", "WebFetch", "WebSearch",
                                                    "Agent", "Skill", "NotebookEdit")),
            unit="threads", output_schema=contracts.path("threads"), runner=runner or run_claude_process)
        answer = extract_json(process.stdout or "")
        if process.returncode != 0 or not isinstance(answer, dict) or not isinstance(answer.get("threads"), list):
            logger.warning("thread finder failed open: exit %s, no threads list", process.returncode)
            return []
    except Exception as exc:
        logger.warning("thread finder failed open: %s", exc)
        return []

    # Each story is checked on its own: one over-long angle must not cost the
    # others (2026-10-10, the first real call lost all of them).
    item_schema = contracts.load("threads")["properties"]["threads"]["items"]
    rows = []
    for row in answer["threads"]:
        problems = contracts.errors(row, item_schema, "$.thread")
        if problems:
            logger.warning("lead story dropped: %s", problems[:2])
        elif row["title"].strip() and row["angle"].strip():
            rows.append(row)
    # Strongest first, so a stronger story keeps a finding two stories both claim.
    rows.sort(key=lambda r: -r["strength"])
    by_id = {e.finding_id: e for e in episodes}
    used: set[int] = set()
    leads = []
    for row in rows:
        if len(leads) == policy.leads:
            break
        members = [by_id[fid] for fid in dict.fromkeys(row["finding_ids"]) if fid in by_id and fid not in used]
        fresh = [m for m in members if m.finding_id not in covered]
        if len(fresh) < policy.min_members or len({m.agent for m in fresh}) < policy.min_agents:
            logger.info("lead story dropped, %d fresh findings left: %s", len(fresh), row["title"])
            continue
        used.update(m.finding_id for m in members)
        leads.append(Thread(row["title"].strip(), row["angle"].strip(), members, row["strength"]))
    _attach_earlier(conn, today, leads, policy)
    return leads


def _attach_earlier(conn: sqlite3.Connection, today: str, threads: list[Thread], policy: ThreadPolicy) -> None:
    """Earlier coverage of a lead story's findings, when the past-links finder has any. Best effort."""
    if not threads:
        return
    try:
        continuations = find_candidates(conn, today, policy)
    except Exception as exc:
        logger.warning("earlier coverage unavailable: %s", exc)
        return
    earlier_of = {}
    for candidate in continuations:
        for episode in candidate.today:
            earlier_of.setdefault(episode.finding_id, []).extend(candidate.earlier)
    for thread in threads:
        seen = {}
        for member in thread.members:
            for episode in earlier_of.get(member.finding_id, []):
                seen[episode.finding_id] = episode
        thread.earlier = sorted(seen.values(), key=lambda e: (e.run_date, e.finding_id))[-6:]


def lead_positions(leads: list[Thread]) -> dict[int, int]:
    """finding id -> the lead story (1-based) it serves, for marking All Findings."""
    return {m.finding_id: n for n, lead in enumerate(leads, 1) for m in lead.members}


def lead_block(leads: list[Thread]) -> str:
    """The writer's lead stories: each angle, its findings with links, and earlier coverage."""
    if not leads:
        return ""
    lines = ["## Lead stories",
             f"The Top stories open with these {len(leads)}, in this order. Each is an original story built from "
             "several findings. No single source wrote it. Write it around its angle under a headline of your own, "
             "bring in each finding's facts with its source link, and say what each one adds. Don't retell the "
             "findings one after another. Use only facts from these findings, the evidence packs, and All "
             "Findings. Where earlier coverage is listed, say what today adds.", ""]
    for n, lead in enumerate(leads, 1):
        lines += [f"### Lead story {n}", f"Working title: {lead.title}", f"Angle: {lead.angle}", "Findings:"]
        lines += [f"- [{m.source_name}]({m.source_url}) {m.title}. {m.summary}" for m in lead.members]
        if lead.earlier:
            lines.append("Earlier coverage:")
            lines += [f"- {e.run_date}: [{e.source_name}]({e.source_url}) {e.title}" for e in lead.earlier]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def deep_dives(leads: list[Thread]) -> list[DeepDive]:
    """One deep dive per lead story, testing its angle against the sources of every finding in it."""
    return [DeepDive(story_id(lead.title), lead.title, None, angle=lead.angle,
                     members=[asdict(m) for m in lead.members]) for lead in leads]


def save(threads: list[Thread], *, date_str: str, user: str, reports_root: Path) -> Path:
    """reports/<user>/threads/<date>.json, the record of what led the issue and why."""
    path = reports_root / user / "threads" / f"{date_str}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": date_str, "threads": [asdict(t) for t in threads]}, indent=2) + "\n")
    return path
