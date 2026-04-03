"""
Pure algorithms for knowledge graph operations. No file I/O.

Provides: section tree parsing, suffix-index ref resolution, 5-tier fuzzy
search, Levenshtein distance, code-ref scanning, and frontmatter helpers.

All functions are deterministic — no LLM, no network, no side effects.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# ── Data structures ──────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Section:
    """A parsed section from a knowledge markdown file."""
    id: str
    depth: int
    heading: str
    start_line: int
    end_line: int
    first_paragraph: str
    body: str
    children: tuple[Section, ...] = ()


@dataclass(frozen=True, slots=True)
class Ref:
    """A resolved wiki-link reference."""
    raw: str
    file_slug: str
    section_fragment: str | None
    resolved_path: str | None
    resolved_section_id: str | None
    ambiguous: bool
    source_file: str
    source_line: int


@dataclass(frozen=True, slots=True)
class CodeRef:
    """A @know comment found in Python source."""
    target: str
    source_file: str
    source_line: int


@dataclass
class CheckResult:
    """Result of a validation pass."""
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"pass": self.passed, "failures": self.failures, "warnings": self.warnings}


# ── Constants ────────────────────────────────────────────────────────

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
KNOW_RE = re.compile(r"#\s*@know:\s*\[\[([^\]]+)\]\]")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
REQUIRE_CODE_RE = re.compile(r"require-code-mention:\s*true", re.IGNORECASE)
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
FIRST_PARA_MAX = 250


# ── Section tree parser ──────────────────────────────────────────────

@dataclass
class _SectionBuilder:
    """Mutable builder for constructing frozen Section objects."""
    depth: int
    heading: str
    start_line: int
    id_parts: list[str]
    lines: list[str] = field(default_factory=list)
    child_builders: list[_SectionBuilder] = field(default_factory=list)
    _end_line: int = 0

    def build(self, end_line: int) -> Section:
        body = "\n".join(self.lines)
        first_para = _extract_first_paragraph(body)
        children = tuple(
            cb.build(cb._compute_end_line(end_line))
            for cb in self.child_builders
        )
        return Section(
            id="#".join(self.id_parts),
            depth=self.depth,
            heading=self.heading,
            start_line=self.start_line,
            end_line=end_line,
            first_paragraph=first_para,
            body=body,
            children=children,
        )

    def _compute_end_line(self, parent_end: int) -> int:
        """Compute end line from the next sibling or parent end."""
        return parent_end


def _extract_first_paragraph(body: str) -> str:
    """Extract the first non-empty paragraph from section body text."""
    lines = body.split("\n")
    para_lines: list[str] = []
    started = False

    for line in lines:
        stripped = line.strip()
        # Skip heading lines
        if HEADING_RE.match(stripped):
            continue
        if not stripped:
            if started:
                break
            continue
        started = True
        para_lines.append(stripped)

    text = " ".join(para_lines)
    # Strip wiki-link markup for length measurement
    text_for_len = WIKI_LINK_RE.sub("", text)
    if len(text_for_len) > FIRST_PARA_MAX:
        # Truncate the raw text proportionally
        ratio = FIRST_PARA_MAX / len(text_for_len)
        cut = int(len(text) * ratio)
        text = text[:cut].rstrip() + "..."
    return text


def _skip_frontmatter(lines: list[str]) -> int:
    """Return the line index where content starts (after frontmatter)."""
    if not lines or lines[0].strip() != "---":
        return 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i + 1
    return 0


def parse_sections(text: str, file_slug: str) -> list[Section]:
    """Parse markdown text into a hierarchical list of Section objects.

    Uses a stack-based algorithm. Skips headings inside fenced code blocks
    and YAML frontmatter.

    Args:
        text: Raw markdown content.
        file_slug: e.g. 'orchestrator/runner', used as root of section IDs.

    Returns:
        List of top-level Section objects with nested children.
    """
    lines = text.split("\n")
    content_start = _skip_frontmatter(lines)

    # Stack of (builder, children_of_parent) tuples
    # We use a virtual root at depth 0
    top_level: list[_SectionBuilder] = []
    stack: list[_SectionBuilder] = []
    in_fence = False
    fence_marker = ""

    all_builders: list[_SectionBuilder] = []

    for line_idx in range(content_start, len(lines)):
        line = lines[line_idx]
        line_num = line_idx + 1  # 1-based

        # Track fenced code blocks
        fence_match = FENCE_RE.match(line.strip())
        if fence_match:
            marker = fence_match.group(1)[0]  # ` or ~
            if in_fence:
                if marker == fence_marker:
                    in_fence = False
            else:
                in_fence = True
                fence_marker = marker
            # Add line to current section body
            if stack:
                stack[-1].lines.append(line)
            continue

        if in_fence:
            if stack:
                stack[-1].lines.append(line)
            continue

        # Check for heading
        heading_match = HEADING_RE.match(line)
        if heading_match:
            depth = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            # Pop stack until we find a parent with smaller depth
            while stack and stack[-1].depth >= depth:
                stack.pop()

            # Build ID parts
            if stack:
                id_parts = stack[-1].id_parts + [heading_text]
            else:
                id_parts = [file_slug, heading_text]

            builder = _SectionBuilder(
                depth=depth,
                heading=heading_text,
                start_line=line_num,
                id_parts=list(id_parts),
            )
            all_builders.append(builder)

            if stack:
                stack[-1].child_builders.append(builder)
            else:
                top_level.append(builder)

            stack.append(builder)
        else:
            # Regular line — add to current section
            if stack:
                stack[-1].lines.append(line)

    # Compute end lines: each builder ends where the next sibling starts - 1,
    # or at the end of the file
    total_lines = len(lines)
    _assign_end_lines(all_builders, total_lines)

    # Build the tree
    return [b.build(b._end_line) for b in top_level]


def _assign_end_lines(builders: list[_SectionBuilder], total_lines: int) -> None:
    """Assign _end_line to each builder based on the next builder's start."""
    for i, b in enumerate(builders):
        if i + 1 < len(builders):
            b._end_line = builders[i + 1].start_line - 1
        else:
            b._end_line = total_lines
        # Recurse into children isn't needed — all_builders is already flat
        # and ordered by start_line


def flatten_sections(sections: list[Section]) -> list[Section]:
    """Flatten a section tree into a list (pre-order traversal)."""
    result: list[Section] = []
    for s in sections:
        result.append(s)
        result.extend(flatten_sections(list(s.children)))
    return result


# ── Suffix index ─────────────────────────────────────────────────────

def build_suffix_index(slug_to_path: dict[str, str]) -> dict[str, list[str]]:
    """Build a case-insensitive suffix index from slug → path mappings.

    For each slug like 'orchestrator/runner', indexes all suffixes:
    'orchestrator/runner' and 'runner'. Keys are lowercased.
    When a suffix maps to >1 path, that suffix is ambiguous.

    Args:
        slug_to_path: Maps slugs to file paths.

    Returns:
        Dict mapping lowercased suffix strings to lists of (slug, path) tuples.
    """
    index: dict[str, list[tuple[str, str]]] = {}

    for slug, path in slug_to_path.items():
        # Generate all suffixes of the slug split by '/'
        parts = slug.split("/")
        for i in range(len(parts)):
            suffix = "/".join(parts[i:]).lower()
            if suffix not in index:
                index[suffix] = []
            index[suffix].append((slug, path))

            # Also index underscore-to-hyphen normalized variant
            normalized = suffix.replace("_", "-")
            if normalized != suffix:
                if normalized not in index:
                    index[normalized] = []
                if (slug, path) not in index[normalized]:
                    index[normalized].append((slug, path))

    return index


def resolve_ref(
    raw_ref: str,
    suffix_index: dict[str, list[tuple[str, str]]],
    section_index: dict[str, Section] | None = None,
) -> tuple[str | None, str | None, bool]:
    """Resolve a wiki-link reference to a file path and optional section.

    Args:
        raw_ref: Text inside [[ ]], e.g. 'orchestrator/runner#Error Handling'.
        suffix_index: From build_suffix_index().
        section_index: Optional dict mapping section IDs to Section objects.

    Returns:
        (resolved_slug, resolved_section_id, ambiguous)
    """
    # Split on first #
    if "#" in raw_ref:
        file_part, section_fragment = raw_ref.split("#", 1)
    else:
        file_part = raw_ref
        section_fragment = None

    # Normalize: underscores → hyphens (knowledge files use hyphens)
    file_key = file_part.lower().strip().replace("_", "-")

    # Look up in suffix index
    matches = suffix_index.get(file_key, [])

    if not matches:
        return None, None, False

    if len(matches) > 1:
        # Ambiguous — but check if only one has the requested section
        if section_fragment and section_index:
            narrowed = []
            for slug, path in matches:
                candidate_id = f"{slug}#{section_fragment}"
                if candidate_id in section_index:
                    narrowed.append((slug, path))
            if len(narrowed) == 1:
                slug, path = narrowed[0]
                section_id = f"{slug}#{section_fragment}"
                return slug, section_id, False

        return matches[0][0], None, True

    slug, path = matches[0]

    if section_fragment and section_index:
        # Try exact section match
        section_id = f"{slug}#{section_fragment}"
        if section_id in section_index:
            return slug, section_id, False

        # Try case-insensitive search through sections for this file
        frag_lower = section_fragment.lower()
        for sid, sec in section_index.items():
            if sid.lower().startswith(slug.lower() + "#") and sid.lower().endswith("#" + frag_lower):
                return slug, sid, False
            # Also try direct tail match
            parts = sid.split("#")
            if len(parts) >= 2 and parts[-1].lower() == frag_lower and sid.lower().startswith(slug.lower()):
                return slug, sid, False

        # Section not found — file resolves but section doesn't
        return slug, None, False

    return slug, None, False


# ── 5-tier fuzzy search ──────────────────────────────────────────────

def find_sections(
    query: str,
    section_ids: list[str],
    max_results: int = 10,
) -> list[tuple[str, int, float]]:
    """Search section IDs with 5-tier matching.

    Tiers:
    1. Exact match on full section ID (case-insensitive).
    2. File stem expansion (query matches slug portion).
    3. Subsection tail match (query = last #-segment).
    4. Subsequence match (query segments in order within ID segments).
    5. Levenshtein fuzzy match (threshold: 40% of max length).

    Returns:
        List of (section_id, tier, score) sorted by tier asc, score desc.
    """
    results: list[tuple[str, int, float]] = []
    query_lower = query.lower().strip()

    if not query_lower:
        return []

    seen = set()

    # Tier 1: Exact match
    for sid in section_ids:
        if sid.lower() == query_lower:
            seen.add(sid)
            results.append((sid, 1, 1.0))

    # Tier 2: File stem match — query matches the file/slug portion (before first #)
    for sid in section_ids:
        if sid in seen:
            continue
        slug_part = sid.split("#")[0].lower()
        # Check if query matches a suffix of the slug
        slug_suffixes = slug_part.split("/")
        for i in range(len(slug_suffixes)):
            if "/".join(slug_suffixes[i:]) == query_lower:
                seen.add(sid)
                results.append((sid, 2, 0.9))
                break

    # Tier 3: Tail match — query matches the last #-delimited segment
    for sid in section_ids:
        if sid in seen:
            continue
        parts = sid.split("#")
        if len(parts) >= 2 and parts[-1].lower() == query_lower:
            seen.add(sid)
            results.append((sid, 3, 0.8))

    # Tier 4: Subsequence match — query #-segments appear in order in ID
    query_segments = [s.lower() for s in re.split(r"[#/]", query) if s]
    if len(query_segments) > 1:
        for sid in section_ids:
            if sid in seen:
                continue
            id_segments = [s.lower() for s in re.split(r"[#/]", sid) if s]
            if _is_subsequence(query_segments, id_segments):
                score = len(query_segments) / max(len(id_segments), 1)
                seen.add(sid)
                results.append((sid, 4, score))

    # Tier 5: Levenshtein fuzzy match
    for sid in section_ids:
        if sid in seen:
            continue
        # Compare against the heading portion (after file slug)
        heading_part = "#".join(sid.split("#")[1:]).lower() if "#" in sid else sid.lower()
        compare_target = heading_part if heading_part else sid.lower()

        dist = levenshtein_distance(query_lower, compare_target)
        max_len = max(len(query_lower), len(compare_target))
        threshold = 0.4 * max_len

        if max_len > 0 and dist <= threshold:
            score = 1.0 - (dist / max_len)
            seen.add(sid)
            results.append((sid, 5, score))

    # Sort by tier ascending, then score descending
    results.sort(key=lambda x: (x[1], -x[2]))
    return results[:max_results]


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    """Check if needle segments appear in order within haystack (substring match)."""
    j = 0
    for h in haystack:
        if j < len(needle) and needle[j] in h:
            j += 1
    return j == len(needle)


# ── Levenshtein distance ─────────────────────────────────────────────

def levenshtein_distance(s: str, t: str) -> int:
    """Compute Levenshtein edit distance. Two-row DP, O(min(m,n)) space."""
    if len(s) > len(t):
        s, t = t, s

    m, n = len(s), len(t)
    if m == 0:
        return n

    prev = list(range(m + 1))
    curr = [0] * (m + 1)

    for j in range(1, n + 1):
        curr[0] = j
        for i in range(1, m + 1):
            cost = 0 if s[i - 1] == t[j - 1] else 1
            curr[i] = min(
                curr[i - 1] + 1,      # insertion
                prev[i] + 1,          # deletion
                prev[i - 1] + cost,   # substitution
            )
        prev, curr = curr, prev

    return prev[m]


# ── Code reference scanner ───────────────────────────────────────────

DEFAULT_EXCLUDE_DIRS = [".git", "__pycache__", "node_modules", ".venv", ".claude"]


def scan_code_refs(
    project_root: str,
    exclude_dirs: list[str] | None = None,
) -> list[CodeRef]:
    """Scan Python source files for # @know: [[target]] comments.

    Tries ripgrep first for speed, falls back to pathlib walking.
    """
    excludes = exclude_dirs or DEFAULT_EXCLUDE_DIRS
    refs = _scan_with_ripgrep(project_root, excludes)
    if refs is not None:
        return refs
    return _scan_with_pathlib(project_root, excludes)


def _scan_with_ripgrep(project_root: str, exclude_dirs: list[str]) -> list[CodeRef] | None:
    """Try scanning with ripgrep. Returns None if rg unavailable."""
    exclude_args: list[str] = []
    for d in exclude_dirs:
        exclude_args.extend(["--glob", f"!{d}"])

    try:
        result = subprocess.run(
            ["rg", "--no-heading", "--line-number", "--type", "py",
             r"#\s*@know:\s*\[\[", *exclude_args, project_root],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode > 1:
            return None
        return _parse_rg_output(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _parse_rg_output(output: str) -> list[CodeRef]:
    """Parse ripgrep output lines: path:line:content."""
    refs: list[CodeRef] = []
    for line in output.strip().splitlines():
        if not line:
            continue
        # Format: /path/to/file.py:42:# @know: [[target]]
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        filepath, linenum, content = parts[0], parts[1], parts[2]
        m = KNOW_RE.search(content)
        if m:
            refs.append(CodeRef(
                target=m.group(1),
                source_file=filepath,
                source_line=int(linenum),
            ))
    return refs


def _scan_with_pathlib(project_root: str, exclude_dirs: list[str]) -> list[CodeRef]:
    """Walk directory tree with pathlib. Slower but always works."""
    refs: list[CodeRef] = []
    root = Path(project_root)

    for py_file in root.rglob("*.py"):
        if any(excluded in py_file.parts for excluded in exclude_dirs):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = KNOW_RE.search(line)
            if m:
                refs.append(CodeRef(
                    target=m.group(1),
                    source_file=str(py_file),
                    source_line=i,
                ))
    return refs


# ── Frontmatter helpers ──────────────────────────────────────────────

def has_require_code_mention(text: str) -> bool:
    """Check if markdown file has require-code-mention: true in frontmatter."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return False
    return bool(REQUIRE_CODE_RE.search(m.group(1)))


def strip_wiki_links_for_length(text: str) -> str:
    """Strip [[...]] markup for character counting."""
    return WIKI_LINK_RE.sub("", text)
