"""
Knowledge graph for the harness. Deterministic operations:

- check(): validate all [[wiki-links]] resolve (file + section level), validate
  section content, INDEX.md completeness, and @know code references
- expand(ref): return content of a knowledge file/section + linked files
- search(query): 5-tier fuzzy search across all section IDs, with keyword fallback
- evolve(stage, data): update knowledge files after a harness stage
- summary(): return INDEX.md + all issues + patterns (for scout prompt injection)
- parse(slug): show the section tree for a knowledge file
- locate(query): find sections via tiered matching
- refs(slug): show incoming and outgoing references for a file

Deterministic — no LLM, no network, no side effects (except evolve/summary I/O).
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from harness.knowledge_sections import (
    CheckResult,
    Section,
    build_suffix_index,
    find_sections,
    flatten_sections,
    has_require_code_mention,
    parse_sections,
    resolve_ref,
    scan_code_refs,
    strip_wiki_links_for_length,
    WIKI_LINK_RE,
)

log = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
PROJECT_ROOT = Path(__file__).parent.parent.resolve()


# ── File I/O helpers ─────────────────────────────────────────────────

def _slug_to_path(slug: str, knowledge_dir: Path | None = None) -> Path:
    """Convert a wiki-link slug to a file path.
    [[orchestrator/runner]] -> knowledge/orchestrator-runner.md
    """
    kdir = knowledge_dir or KNOWLEDGE_DIR
    filename = slug.replace("/", "-").replace("_", "-") + ".md"
    return kdir / filename


def _path_to_slug(path: Path) -> str:
    """Convert a file path back to a wiki-link slug."""
    name = path.stem
    for prefix in ("orchestrator", "social", "memory", "slack-bot", "slack_bot",
                    "harness", "data", "agents", "issues", "patterns", "runs"):
        if name.startswith(prefix + "-"):
            rest = name[len(prefix) + 1:]
            return f"{prefix}/{rest}"
    return name


def list_files(knowledge_dir: Path | None = None) -> list[Path]:
    """List all knowledge files."""
    kdir = knowledge_dir or KNOWLEDGE_DIR
    return sorted(kdir.glob("*.md"))


def _read_file(path: Path) -> str:
    """Read a knowledge file, return '' if missing."""
    if path.exists():
        return path.read_text()
    return ""


# ── Index building ───────────────────────────────────────────────────

def _build_indexes(
    knowledge_dir: Path | None = None,
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, Section], dict[str, list[Section]]]:
    """Build suffix index, section index, and per-file section lists.

    Returns:
        (suffix_index, section_id_to_section, slug_to_sections)
    """
    kdir = knowledge_dir or KNOWLEDGE_DIR
    files = list_files(kdir)

    # Build slug → path mapping
    slug_to_path: dict[str, str] = {}
    for f in files:
        slug = _path_to_slug(f)
        slug_to_path[slug] = str(f)

    suffix_index = build_suffix_index(slug_to_path)

    # Parse all files into section trees
    section_index: dict[str, Section] = {}
    slug_to_sections: dict[str, list[Section]] = {}

    for f in files:
        slug = _path_to_slug(f)
        text = f.read_text()
        sections = parse_sections(text, slug)
        slug_to_sections[slug] = sections
        for s in flatten_sections(sections):
            section_index[s.id] = s

    return suffix_index, section_index, slug_to_sections


# ── Validation passes ────────────────────────────────────────────────

def check_refs(
    knowledge_dir: Path,
    suffix_index: dict[str, list[tuple[str, str]]],
    section_index: dict[str, Section],
) -> CheckResult:
    """Validate all [[wiki-links]] resolve to real files and sections."""
    failures: list[str] = []
    warnings: list[str] = []

    for path in list_files(knowledge_dir):
        text = path.read_text()
        for match in WIKI_LINK_RE.finditer(text):
            raw = match.group(1)
            slug, section_id, ambiguous = resolve_ref(raw, suffix_index, section_index)

            if slug is None:
                failures.append(f"{path.name}: broken link [[{raw}]] — no matching file")
            elif ambiguous:
                warnings.append(f"{path.name}: ambiguous link [[{raw}]] — multiple files match")
            elif "#" in raw and section_id is None:
                fragment = raw.split("#", 1)[1]
                warnings.append(f"{path.name}: [[{raw}]] — file found but section '{fragment}' not found")

    return CheckResult(
        passed=len(failures) == 0,
        failures=failures,
        warnings=warnings,
    )


def check_sections(
    slug_to_sections: dict[str, list[Section]],
) -> CheckResult:
    """Validate all sections have leading paragraphs <= 250 chars."""
    failures: list[str] = []
    warnings: list[str] = []

    for slug, sections in slug_to_sections.items():
        for s in flatten_sections(sections):
            if not s.first_paragraph:
                warnings.append(f"{s.id}: empty leading paragraph")
            else:
                text_len = len(strip_wiki_links_for_length(s.first_paragraph))
                if text_len > 250:
                    failures.append(f"{s.id}: leading paragraph is {text_len} chars (max 250)")

    return CheckResult(
        passed=len(failures) == 0,
        failures=failures,
        warnings=warnings,
    )


def check_index(
    knowledge_dir: Path,
    suffix_index: dict[str, list[tuple[str, str]]],
) -> CheckResult:
    """Validate INDEX.md has entries for all knowledge files and no stale entries."""
    failures: list[str] = []
    warnings: list[str] = []
    index_path = knowledge_dir / "INDEX.md"

    if not index_path.exists():
        return CheckResult(passed=False, failures=["INDEX.md not found"])

    index_text = index_path.read_text()
    index_links: set[str] = set()
    index_links_raw: set[str] = set()
    for match in WIKI_LINK_RE.finditer(index_text):
        raw = match.group(1)
        index_links_raw.add(raw.lower())
        # Normalize underscores to hyphens for matching
        index_links.add(raw.lower().replace("_", "-"))

    # Check all non-INDEX files have an entry
    for path in list_files(knowledge_dir):
        if path.name == "INDEX.md":
            continue
        slug = _path_to_slug(path)
        # Normalize both sides for comparison
        slug_normalized = slug.lower().replace("_", "-")
        if slug_normalized not in index_links:
            failures.append(f"INDEX.md missing entry for {slug} ({path.name})")

    # Check no stale entries
    for link in index_links:
        resolved_slug, _, ambig = resolve_ref(link, suffix_index)
        if resolved_slug is None:
            failures.append(f"INDEX.md has stale entry [[{link}]] — file not found")

    return CheckResult(
        passed=len(failures) == 0,
        failures=failures,
        warnings=warnings,
    )


def check_code_refs(
    project_root: Path,
    knowledge_dir: Path,
    suffix_index: dict[str, list[tuple[str, str]]],
    section_index: dict[str, Section],
    slug_to_sections: dict[str, list[Section]],
) -> CheckResult:
    """Validate @know comments resolve and require-code-mention is enforced."""
    failures: list[str] = []
    warnings: list[str] = []

    code_refs = scan_code_refs(str(project_root))

    # Validate each @know comment resolves
    code_ref_targets: set[str] = set()
    for ref in code_refs:
        slug, section_id, ambig = resolve_ref(ref.target, suffix_index, section_index)
        if slug is None:
            failures.append(f"{ref.source_file}:{ref.source_line}: @know [[{ref.target}]] — no matching file")
        elif "#" in ref.target and section_id is None:
            fragment = ref.target.split("#", 1)[1]
            warnings.append(f"{ref.source_file}:{ref.source_line}: @know [[{ref.target}]] — section '{fragment}' not found")
        else:
            # Track resolved targets for require-code-mention enforcement
            if section_id:
                code_ref_targets.add(section_id.lower())
            if slug:
                code_ref_targets.add(slug.lower())

    # Check require-code-mention enforcement
    for path in list_files(knowledge_dir):
        if path.name == "INDEX.md":
            continue
        text = path.read_text()
        if not has_require_code_mention(text):
            continue

        slug = _path_to_slug(path)
        sections = slug_to_sections.get(slug, [])
        leaf_sections = [s for s in flatten_sections(sections) if not s.children]

        for leaf in leaf_sections:
            if leaf.id.lower() not in code_ref_targets:
                failures.append(f"{path.name}: require-code-mention — section '{leaf.heading}' ({leaf.id}) has no @know reference in code")

    return CheckResult(
        passed=len(failures) == 0,
        failures=failures,
        warnings=warnings,
    )


def check(knowledge_dir: Path | None = None) -> dict:
    """Run all validation passes. Returns backward-compatible dict.

    Return shape:
        {
            "pass": bool,
            "broken": [...],  # backward compat — same as old check()
            "valid": int,
            "total": int,
            "results": {
                "refs": {"pass": bool, "failures": [...], "warnings": [...]},
                "sections": {"pass": bool, ...},
                "index": {"pass": bool, ...},
                "code_refs": {"pass": bool, ...},
            }
        }
    """
    kdir = knowledge_dir or KNOWLEDGE_DIR
    suffix_index, section_index, slug_to_sections = _build_indexes(kdir)

    refs_result = check_refs(kdir, suffix_index, section_index)
    sections_result = check_sections(slug_to_sections)
    index_result = check_index(kdir, suffix_index)
    code_refs_result = check_code_refs(PROJECT_ROOT, kdir, suffix_index, section_index, slug_to_sections)

    all_passed = all([
        refs_result.passed,
        sections_result.passed,
        index_result.passed,
        code_refs_result.passed,
    ])

    # Backward compatibility: build the old broken/valid/total fields
    broken = []
    valid = 0
    total = 0
    for path in list_files(kdir):
        text = path.read_text()
        for match in WIKI_LINK_RE.finditer(text):
            total += 1
            slug = match.group(1)
            target = _slug_to_path(slug, kdir)
            if target.exists():
                valid += 1
            else:
                broken.append({
                    "source": path.name,
                    "link": slug,
                    "expected": str(target),
                })

    return {
        "pass": all_passed,
        "broken": broken,
        "valid": valid,
        "total": total,
        "results": {
            "refs": refs_result.to_dict(),
            "sections": sections_result.to_dict(),
            "index": index_result.to_dict(),
            "code_refs": code_refs_result.to_dict(),
        },
    }


# ── Search ───────────────────────────────────────────────────────────

def search(query: str, knowledge_dir: Path | None = None, max_results: int = 10) -> list[dict]:
    """5-tier fuzzy search across section IDs, with keyword fallback.

    Returns list of {section_id, tier, score, first_paragraph, file, slug}.
    Falls back to keyword search when fuzzy produces no results.
    """
    kdir = knowledge_dir or KNOWLEDGE_DIR
    suffix_index, section_index, slug_to_sections = _build_indexes(kdir)

    all_section_ids = list(section_index.keys())
    fuzzy_results = find_sections(query, all_section_ids, max_results)

    if fuzzy_results:
        results = []
        for section_id, tier, score in fuzzy_results:
            section = section_index[section_id]
            slug = section_id.split("#")[0]
            results.append({
                "section_id": section_id,
                "tier": tier,
                "score": round(score, 3),
                "first_paragraph": section.first_paragraph,
                "file": _slug_to_path(slug, kdir).name,
                "slug": slug,
            })
        return results

    # Keyword fallback (preserves old behavior)
    return _keyword_search(query, kdir)


def _keyword_search(query: str, knowledge_dir: Path) -> list[dict]:
    """Naive keyword search — fallback when fuzzy search returns nothing."""
    query_words = query.lower().split()
    results = []

    for path in list_files(knowledge_dir):
        content = path.read_text()
        content_lower = content.lower()
        score = sum(1 for w in query_words if w in content_lower)
        if score == 0:
            continue

        lines = content.split("\n")
        context_line = ""
        for line in lines:
            if any(w in line.lower() for w in query_words):
                context_line = line.strip()[:200]
                break

        results.append({
            "file": path.name,
            "slug": _path_to_slug(path),
            "score": score,
            "context": context_line,
        })

    return sorted(results, key=lambda r: r["score"], reverse=True)


# ── Expand ───────────────────────────────────────────────────────────

def expand(slug: str, depth: int = 1, knowledge_dir: Path | None = None) -> str:
    """Return content of a knowledge file/section + linked files.

    Supports section-level expansion: expand("orchestrator/runner#Error Handling")
    returns just that section's content.

    For backward compatibility, returns a string. The section tree is embedded
    as markdown with hierarchical headings.
    """
    kdir = knowledge_dir or KNOWLEDGE_DIR

    # Check if slug contains a section reference
    if "#" in slug:
        file_slug, section_fragment = slug.split("#", 1)
    else:
        file_slug = slug
        section_fragment = None

    path = _slug_to_path(file_slug, kdir)
    if not path.exists():
        return f"[NOT FOUND: {slug}]"

    content = path.read_text()

    # If section requested, extract just that section
    if section_fragment:
        sections = parse_sections(content, file_slug)
        flat = flatten_sections(sections)
        for s in flat:
            # Match by heading (case-insensitive)
            if s.heading.lower() == section_fragment.lower():
                return f"# {slug}\n\n{'#' * s.depth} {s.heading}\n\n{s.body}\n"
            # Match by full ID
            if s.id.lower() == slug.lower():
                return f"# {slug}\n\n{'#' * s.depth} {s.heading}\n\n{s.body}\n"
        return f"[SECTION NOT FOUND: {slug}]"

    if depth <= 0:
        return content

    # Expand linked files (1 level deep)
    parts = [f"# {slug}\n\n{content}\n"]
    seen = {slug}

    for match in WIKI_LINK_RE.finditer(content):
        linked_slug = match.group(1)
        if linked_slug in seen:
            continue
        seen.add(linked_slug)

        linked_path = _slug_to_path(linked_slug, kdir)
        if linked_path.exists():
            linked_content = linked_path.read_text()
            parts.append(f"\n---\n# (linked) {linked_slug}\n\n{linked_content}\n")

    return "\n".join(parts)


# ── Parse (new) ──────────────────────────────────────────────────────

def parse(slug: str, knowledge_dir: Path | None = None) -> list[Section]:
    """Parse a knowledge file into its section tree."""
    kdir = knowledge_dir or KNOWLEDGE_DIR
    path = _slug_to_path(slug, kdir)
    if not path.exists():
        return []
    text = path.read_text()
    return parse_sections(text, slug)


# ── Refs (new) ───────────────────────────────────────────────────────

def refs(slug: str, knowledge_dir: Path | None = None) -> dict:
    """Show incoming and outgoing references for a knowledge file.

    Returns:
        {
            "outgoing": [{"target": str, "line": int}],
            "incoming": [{"source_file": str, "source_slug": str, "line": int}],
        }
    """
    kdir = knowledge_dir or KNOWLEDGE_DIR
    path = _slug_to_path(slug, kdir)
    result = {"outgoing": [], "incoming": []}

    if not path.exists():
        return result

    # Outgoing: links in this file
    text = path.read_text()
    for i, line in enumerate(text.splitlines(), 1):
        for match in WIKI_LINK_RE.finditer(line):
            result["outgoing"].append({"target": match.group(1), "line": i})

    # Incoming: links from other files pointing to this slug
    slug_lower = slug.lower()
    for other_path in list_files(kdir):
        if other_path == path:
            continue
        other_text = other_path.read_text()
        other_slug = _path_to_slug(other_path)
        for i, line in enumerate(other_text.splitlines(), 1):
            for match in WIKI_LINK_RE.finditer(line):
                target = match.group(1)
                # Check if this link points to our slug
                target_file = target.split("#")[0] if "#" in target else target
                if target_file.lower().replace("/", "-").replace("_", "-") == slug.lower().replace("/", "-").replace("_", "-"):
                    result["incoming"].append({
                        "source_file": other_path.name,
                        "source_slug": other_slug,
                        "line": i,
                    })

    return result


# ── Summary (unchanged) ──────────────────────────────────────────────

def summary() -> str:
    """Return a compact summary for injection into scout/agent prompts.
    Includes: shared issue log + INDEX + issues + patterns.
    Shared issue log is first — highest priority context for fix agents.
    """
    parts = []

    issues_log = Path(__file__).parent / "ISSUES.md"
    if issues_log.exists():
        parts.append(issues_log.read_text())

    index_path = KNOWLEDGE_DIR / "INDEX.md"
    if index_path.exists():
        parts.append("\n---\n" + index_path.read_text())

    issues_path = KNOWLEDGE_DIR / "issues-open.md"
    if issues_path.exists():
        parts.append("\n---\n" + issues_path.read_text())

    fails_path = KNOWLEDGE_DIR / "patterns-what-fails.md"
    if fails_path.exists():
        parts.append("\n---\n" + fails_path.read_text())

    works_path = KNOWLEDGE_DIR / "patterns-what-works.md"
    if works_path.exists():
        parts.append("\n---\n" + works_path.read_text())

    latest_path = KNOWLEDGE_DIR / "runs-latest.md"
    if latest_path.exists():
        parts.append("\n---\n" + latest_path.read_text())

    return "\n".join(parts)


# ── Evolve (unchanged) ───────────────────────────────────────────────

def evolve(stage: str, data: dict) -> list[str]:
    """Update knowledge files after a harness stage. Returns list of files updated.

    Stages:
    - scout_done: update issues/open with new tickets found
    - fix_done: update runs/latest with ticket outcomes
    - review_done: update patterns from PR outcomes
    - run_complete: update runs/latest with final summary
    """
    updated = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if stage == "scout_done":
        updated += _evolve_scout(data, now)
    elif stage == "fix_done":
        updated += _evolve_fix(data, now)
    elif stage == "review_done":
        updated += _evolve_review(data, now)
    elif stage == "run_complete":
        updated += _evolve_run_complete(data, now)

    # Re-check links after evolution (uses only ref pass for speed)
    result = check()
    if result["broken"]:
        log.warning("Knowledge graph has %d broken links after evolve(%s)", len(result["broken"]), stage)
        for b in result["broken"]:
            log.warning("  Broken: %s -> [[%s]]", b["source"], b["link"])

    return updated


def _evolve_scout(data: dict, now: str) -> list[str]:
    """Update issues-open.md with newly discovered tickets."""
    tickets = data.get("tickets_created", [])
    if not tickets:
        return []

    issues_path = KNOWLEDGE_DIR / "issues-open.md"
    content = issues_path.read_text() if issues_path.exists() else "# Known Issues\n"

    new_section = f"\n## Scout Findings ({now})\n\n"
    for t in tickets:
        tid = t.get("id", "?")
        title = t.get("title", "?")
        priority = t.get("priority", "P3")
        files = ", ".join(t.get("files_to_modify", []))
        new_section += f"- **[{priority}] {tid}** — {title}. Files: {files}\n"

    content = re.sub(r"## Last Updated.*", f"## Last Updated\n\n{now} — scout added {len(tickets)} findings.", content)
    content += new_section

    issues_path.write_text(content)
    return [str(issues_path)]


def _evolve_fix(data: dict, now: str) -> list[str]:
    """Update runs-latest.md with fix outcomes."""
    latest_path = KNOWLEDGE_DIR / "runs-latest.md"
    content = latest_path.read_text() if latest_path.exists() else "# Latest Harness Run\n"

    ticket_id = data.get("ticket_id", "?")
    status = data.get("status", "unknown")
    reason = data.get("reason", "")
    pr_url = data.get("pr_url", "")

    entry = f"- **{ticket_id}**: {status}"
    if pr_url:
        entry += f" — {pr_url}"
    if reason:
        entry += f" ({reason})"
    entry += "\n"

    if "### Tickets Processed" in content:
        content = content.replace("### Tickets Processed\n", f"### Tickets Processed\n\n{entry}", 1)
    else:
        content += f"\n### Tickets Processed\n\n{entry}"

    if pr_url and "### PRs Created" in content:
        content = content.replace("### PRs Created\n", f"### PRs Created\n\n- {pr_url}\n", 1)

    content = re.sub(r"## Last Updated.*", f"## Last Updated\n\n{now}.", content)
    latest_path.write_text(content)
    return [str(latest_path)]


def _evolve_review(data: dict, now: str) -> list[str]:
    """Update patterns from review outcomes."""
    updated = []
    status = data.get("status", "")
    ticket_id = data.get("ticket_id", "?")
    reason = data.get("reason", "")

    if status == "merged" or status == "pr_created":
        works_path = KNOWLEDGE_DIR / "patterns-what-works.md"
        content = works_path.read_text() if works_path.exists() else "# What Works\n"
        content = re.sub(r"## Last Updated.*", f"## Last Updated\n\n{now}.", content)
        works_path.write_text(content)
        updated.append(str(works_path))

    elif status == "rejected":
        fails_path = KNOWLEDGE_DIR / "patterns-what-fails.md"
        content = fails_path.read_text() if fails_path.exists() else "# What Fails\n"
        content += f"\n- **{ticket_id} rejected** — {reason} ({now})\n"
        content = re.sub(r"## Last Updated.*", f"## Last Updated\n\n{now}.", content)
        fails_path.write_text(content)
        updated.append(str(fails_path))

    return updated


def _evolve_run_complete(data: dict, now: str) -> list[str]:
    """Update runs-latest.md with final summary."""
    latest_path = KNOWLEDGE_DIR / "runs-latest.md"
    content = latest_path.read_text() if latest_path.exists() else "# Latest Harness Run\n"

    processed = data.get("processed", 0)
    prs = data.get("prs", 0)
    failed = data.get("failed", 0)
    remaining = data.get("remaining", 0)

    summary_block = f"""
## Final Summary ({now})

- Processed: {processed}
- PRs created: {prs}
- Failed: {failed}
- Remaining: {remaining}
"""

    content += summary_block
    content = re.sub(r"## Last Updated.*", f"## Last Updated\n\n{now}.", content)
    latest_path.write_text(content)
    return [str(latest_path)]


# ── CLI ──────────────────────────────────────────────────────────────

def _print_section_tree(sections: list[Section], indent: int = 0) -> None:
    """Print a section tree with indentation."""
    for s in sections:
        prefix = "  " * indent
        para = s.first_paragraph[:80] + "..." if len(s.first_paragraph) > 80 else s.first_paragraph
        print(f"{prefix}{'#' * s.depth} {s.heading}  (L{s.start_line}-{s.end_line})")
        if para:
            print(f"{prefix}  {para}")
        _print_section_tree(list(s.children), indent + 1)


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "check":
        result = check()
        # Print backward-compat summary
        print(f"Links: {result['valid']}/{result['total']} valid")
        for b in result["broken"]:
            print(f"  BROKEN: {b['source']} -> [[{b['link']}]]")
        # Print enhanced results
        for name, r in result["results"].items():
            status = "PASS" if r["pass"] else "FAIL"
            print(f"  {name}: {status}")
            for f in r["failures"][:5]:
                print(f"    FAIL: {f}")
            for w in r["warnings"][:5]:
                print(f"    WARN: {w}")
        sys.exit(0 if result["pass"] else 1)

    elif cmd == "summary":
        print(summary())

    elif cmd == "search" and len(sys.argv) > 2:
        query = " ".join(sys.argv[2:])
        results = search(query)
        for r in results:
            if "tier" in r:
                print(f"  [T{r['tier']} {r['score']}] {r['section_id']}")
                if r.get("first_paragraph"):
                    print(f"    {r['first_paragraph'][:100]}")
            else:
                print(f"  [{r['score']}] {r['slug']}: {r['context']}")

    elif cmd == "expand" and len(sys.argv) > 2:
        slug = sys.argv[2]
        print(expand(slug))

    elif cmd == "parse" and len(sys.argv) > 2:
        slug = sys.argv[2]
        sections = parse(slug)
        if not sections:
            print(f"[NOT FOUND: {slug}]")
            sys.exit(1)
        _print_section_tree(sections)

    elif cmd == "locate" and len(sys.argv) > 2:
        query = " ".join(sys.argv[2:])
        _, section_index, _ = _build_indexes()
        all_ids = list(section_index.keys())
        results = find_sections(query, all_ids)
        for sid, tier, score in results:
            print(f"  [T{tier} {score:.3f}] {sid}")

    elif cmd == "refs" and len(sys.argv) > 2:
        slug = sys.argv[2]
        r = refs(slug)
        print(f"Outgoing ({len(r['outgoing'])}):")
        for ref in r["outgoing"]:
            print(f"  L{ref['line']}: [[{ref['target']}]]")
        print(f"Incoming ({len(r['incoming'])}):")
        for ref in r["incoming"]:
            print(f"  {ref['source_slug']} L{ref['line']}")

    elif cmd == "list":
        for f in list_files():
            print(f"  {_path_to_slug(f)}: {f.name}")

    else:
        print("Usage: python -m harness.knowledge_graph <command>")
        print("  check              — validate links, sections, index, code refs")
        print("  summary            — print scout-ready summary")
        print("  search <query>     — 5-tier fuzzy search across sections")
        print("  expand <slug>      — expand a knowledge file (supports #section)")
        print("  parse <slug>       — show section tree for a file")
        print("  locate <query>     — find sections via tiered matching")
        print("  refs <slug>        — show incoming/outgoing references")
        print("  list               — list all knowledge files")
