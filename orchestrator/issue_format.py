"""How an issue is laid out: bullets, lists and tables per Top story and per section. No model calls.

On 2026-10-10 a replay came back with 117 bullets and three tables where the
issue before it had none, and nothing measured it. Layout is a count, so it is
measured here, the same way the prose gate counts em dashes.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from orchestrator.editorial import Layout

_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TABLE_ROW = re.compile(r"^\s*\|")


@dataclass(frozen=True)
class Unit:
    """One Top story (`###` under the Top section) or one other `##` section."""
    kind: str  # "top" or "section"
    heading: str
    words: int
    bullets: int
    lists: int
    tables: int
    longest_list: int
    ends_on_list: bool


def _unit(kind: str, heading: str, lines: list[str]) -> Unit:
    """Count bullets, list blocks and tables. A blank line inside a list doesn't end it; prose does."""
    bullets = lists = tables = longest = run = 0
    in_list = in_table = ends_on_list = False
    for line in lines:
        if not line.strip() or line.strip() == "---":
            in_table = False
            continue
        is_bullet, is_row = bool(_BULLET.match(line)), bool(_TABLE_ROW.match(line))
        in_list = is_bullet or (in_list and line[0] in " \t")
        if is_bullet:
            run = run + 1 if ends_on_list else 1
            lists += run == 1
            longest = max(longest, run)
        bullets += is_bullet
        tables += is_row and not in_table
        in_table, ends_on_list = is_row, in_list
    return Unit(kind, heading, len(" ".join(lines).split()), bullets, lists, tables, longest, ends_on_list)


def measure(markdown: str) -> list[Unit]:
    """One Unit per Top story and per other section with text, in issue order."""
    units: list[Unit] = []
    kind, heading, lines, in_top = "section", "", [], False

    def flush() -> None:
        if heading and " ".join(lines).strip():
            units.append(_unit(kind, heading, lines))

    for line in markdown.splitlines():
        if line.startswith("## "):
            flush()
            kind, heading, lines = "section", line[3:].strip(), []
            in_top = heading.lower().startswith("top ")
        elif in_top and line.startswith("### "):
            flush()
            kind, heading, lines = "top", line[4:].strip(), []
        elif heading:
            lines.append(line)
    flush()
    return units


def report(markdown: str) -> str:
    rows = measure(markdown)
    lines = [f"{'unit':<58} {'words':>6} {'bullets':>7} {'lists':>5} {'tables':>6}"]
    lines += [f"{(u.kind + ' | ' + u.heading)[:58]:<58} {u.words:>6} {u.bullets:>7} {u.lists:>5} {u.tables:>6}"
              for u in rows]
    total = [sum(getattr(u, f) for u in rows) for f in ("words", "bullets", "lists", "tables")]
    lines.append(f"{'total':<58} {total[0]:>6} {total[1]:>7} {total[2]:>5} {total[3]:>6}")
    return "\n".join(lines)


def violations(markdown: str, layout: Layout) -> list[str]:
    """Every place the issue breaks the layout policy, worded as the fix the editor should make."""
    listed = {name.lower() for name in layout.list_sections}
    found = []
    for unit in measure(markdown):
        if unit.kind == "section" and unit.heading.lower() in listed:
            continue
        top = unit.kind == "top"
        where = f'Top story "{unit.heading}"' if top else f'section "{unit.heading}"'
        max_lists = layout.top_max_lists if top else layout.section_max_lists
        max_tables = layout.top_max_tables if top else layout.section_max_tables
        if unit.lists > max_lists:
            found.append(f"layout: {where} has {unit.lists} lists where {max_lists} is allowed; fold the extra "
                         "lists into prose")
        if unit.tables > max_tables:
            found.append(f"layout: {where} has {unit.tables} table(s) where {max_tables} is allowed; write the "
                         "table as prose")
        if top and unit.lists and unit.longest_list > layout.top_max_list_items:
            found.append(f"layout: {where} has a list of {unit.longest_list} items where "
                         f"{layout.top_max_list_items} is allowed; fold the rest into prose")
        if top and unit.lists == 1 and not unit.ends_on_list:
            found.append(f"layout: {where} has a list before its end; fold it into prose")
    return found
