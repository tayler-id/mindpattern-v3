"""`mp`: deterministic tools the research agents (and Tayler) call instead of following prose rules.

    mp finding add <<'EOF' ... EOF    validate, dedupe, and store one finding for this run
    mp findings list                  what this agent has stored so far
    mp seen "<url or title>"          has this been covered in the last 180 days?
    mp fetch <url> [--max-chars N] [--offset N]   readable text of a page, a slice at a time
    mp evidence add --story S <<'EOF' ... EOF     one evidence item for a deep-dive story
    mp lint <file> [--surface S]      writing-policy violations in a draft
    mp tells [--since DAYS]           writing-policy rates across published issues

The add commands read one `field: value` per line on stdin, or JSON with
--json. Agents use the quoted heredoc because Claude Code's Bash check refuses
inline JSON (`{"` reads as expansion obfuscation), while a quoted heredoc passes
apostrophes, `$`, and backticks through untouched.

Agents get these through the `Bash(mp *)` grant. The runner sets MP_FINDINGS_FILE,
MP_EVIDENCE_FILE, MP_USER_ID, MP_RUN_DATE, and MINDPATTERN_AGENT for them.
Every command prints JSON and exits 0 on success, 2 when it rejects input,
1 when it cannot run.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.error
import urllib.request

from core import findings_store

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_DAYS = 180
RECENT_DAYS = 10
DEFAULT_FETCH_CHARS = 6000
_WORD = re.compile(r"[a-z0-9]+")
_FIELD_LINE = re.compile(r"^([a-z_]+):[ \t]*(.*)$")
_STOP = frozenset("a an and are as at be by for from has have in is it its of on or that the this to was were will with".split())


class Rejected(Exception):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _out(payload: dict, code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return code


def _env_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(_out({"ok": False, "error": f"{name} is not set; the pipeline sets it for agents"}, 1))
    return Path(value)


def _user() -> str:
    return os.environ.get("MP_USER_ID") or "ramsay"


def _run_date() -> date:
    value = os.environ.get("MP_RUN_DATE")
    return date.fromisoformat(value) if value else date.today()


def _memory_db() -> Path:
    return PROJECT_ROOT / "data" / _user() / "memory.db"


def normalize_url(url: str) -> str:
    url = url.strip().lower()
    url = re.sub(r"^https?://(www\.)?", "", url)
    url = url.split("#", 1)[0].rstrip("/")
    return url


def title_words(title: str) -> set[str]:
    """Content words of a title. Digits always count: Runtime 1.0 and 2.0 are different stories."""
    return {w for w in _WORD.findall(title.lower()) if w not in _STOP and (len(w) > 1 or w.isdigit())}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def history(query: str, *, db: Path | None = None, today: date | None = None) -> list[dict]:
    """Earlier findings that match a URL exactly or a title closely, newest first."""
    db = db or _memory_db()
    if not db.exists():
        return []
    today = today or _run_date()
    start = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT run_date, agent, title, source_url FROM findings WHERE run_date >= ? AND run_date < ?",
            (start, today.isoformat()),
        ).fetchall()
    finally:
        conn.close()
    is_url = query.strip().lower().startswith(("http://", "https://"))
    matches = []
    if is_url:
        wanted = normalize_url(query)
        for run_date, agent, title, url in rows:
            if url and normalize_url(url) == wanted:
                matches.append({"run_date": run_date, "agent": agent, "title": title, "match": "same url"})
    else:
        words = title_words(query)
        for run_date, agent, title, url in rows:
            score = _jaccard(words, title_words(title or ""))
            if score >= 0.5:
                matches.append({"run_date": run_date, "agent": agent, "title": title,
                                "match": f"title overlap {score:.2f}"})
    return sorted(matches, key=lambda m: m["run_date"], reverse=True)[:5]


def add_finding(finding: object, *, store: Path, agent: str, db: Path | None = None,
                today: date | None = None) -> dict:
    """Validate and store one finding. Raises Rejected with every reason it fails."""
    from core import contracts
    from policies.engine import PolicyEngine

    if not isinstance(finding, dict):
        raise Rejected(["a finding is a JSON object"])
    reasons = contracts.check("research_finding", finding)
    reasons += PolicyEngine.load_research().validate_finding(agent, finding, check_summary_length=False)
    if reasons:
        raise Rejected(reasons)
    stored = findings_store.read_rows(store)
    url, words = normalize_url(finding["source_url"]), title_words(finding["title"])
    for row in stored:
        if normalize_url(row.get("source_url", "")) == url:
            raise Rejected([f"already stored this run: {row.get('title')!r} has the same source_url"])
        if _jaccard(words, title_words(row.get("title", ""))) >= 0.8:
            raise Rejected([f"already stored this run under a near-identical title: {row.get('title')!r}"])
    today = today or _run_date()
    recent = [m for m in history(finding["source_url"], db=db, today=today)
              if m["run_date"] >= (today - timedelta(days=RECENT_DAYS)).isoformat()]
    if recent:
        raise Rejected([f"covered on {recent[0]['run_date']} by {recent[0]['agent']}: {recent[0]['title']!r}. "
                        "Store it only with genuinely new facts, under the new source's URL."])
    findings_store.append(store, {**finding, "agent": agent,
                                  "stored_at": datetime.now().isoformat(timespec="seconds")})
    return {"accepted": True, "stored": len(stored) + 1}


read_findings = findings_store.read_findings


def parse_fields(text: str) -> dict[str, str]:
    """One `field: value` per line. A line without a field name continues the previous value."""
    record: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        match = _FIELD_LINE.match(line)
        if match:
            key = match.group(1)
            if key in record:
                raise Rejected([f"{key} is given twice"])
            record[key] = match.group(2).strip()
        elif line.strip():
            if key is None:
                raise Rejected([f"expected 'field: value', got {line.strip()[:60]!r}"])
            record[key] = f"{record[key]} {line.strip()}".strip()
    if not record:
        raise Rejected(["no fields given; pass one 'field: value' per line"])
    return record


def page_text(raw: str, content_type: str) -> str:
    if "html" not in content_type:
        return raw
    text = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header|form)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|article|section)>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def fetch(url: str, *, max_chars: int = DEFAULT_FETCH_CHARS, offset: int = 0, timeout: int = 20) -> dict:
    if not url.lower().startswith(("http://", "https://")):
        raise Rejected(["only http and https URLs can be fetched"])
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MindPattern research; mp fetch)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        status = response.status
    text = page_text(raw, content_type)
    end = offset + max_chars
    return {"url": url, "status": status, "chars": len(text), "truncated": len(text) > end,
            "next_offset": end if len(text) > end else None, "text": text[offset:end]}


def add_evidence(item: object, *, story: str, store: Path) -> dict:
    from core import contracts

    reasons = contracts.check("evidence_item", item)
    if reasons:
        raise Rejected(reasons)
    stored = [row for row in findings_store.read_rows(store) if row.get("story") == story]
    for row in stored:
        if normalize_url(row.get("source_url", "")) == normalize_url(item["source_url"]) and \
                row.get("claim") == item["claim"]:
            raise Rejected(["this evidence item is already stored for the story"])
    findings_store.append(store, {**item, "story": story})
    return {"accepted": True, "story": story, "stored": len(stored) + 1}


def tells(*, since_days: int, surface: str, reports: Path, today: date | None = None) -> dict:
    """Each writing-policy rule's count and rate across published issues."""
    from orchestrator import word_bank

    today = today or date.today()
    start = (today - timedelta(days=since_days)).isoformat()
    issues = sorted(p for p in reports.glob("*.md")
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", p.name) and p.stem >= start)
    text = "\n".join(p.read_text(errors="replace") for p in issues)
    words = max(len(text.split()), 1)
    rows = []
    for hit in word_bank.scan(text, surface):
        entry = hit.entry
        rate = hit.count * 10_000 / words
        rows.append({"term": entry.term, "tier": entry.tier, "count": hit.count, "per_10k": round(rate, 2),
                     "cap_per_10k": entry.cap_per_10k if entry.tier == "cap" else 0,
                     "over": entry.tier == "ban" or rate > entry.cap_per_10k,
                     "models": list(entry.models), "review_by": entry.review_by})
    rows.sort(key=lambda r: (not r["over"], -r["per_10k"]))
    return {"issues": len(issues), "words": words, "since": start, "surface": surface, "rules": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mp", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    finding = commands.add_parser("finding").add_subparsers(dest="action", required=True)
    finding_add = finding.add_parser("add")
    finding_add.add_argument("--json", help="the finding as JSON (default: field lines on stdin)")
    findings = commands.add_parser("findings").add_subparsers(dest="action", required=True)
    findings.add_parser("list")
    seen = commands.add_parser("seen")
    seen.add_argument("query")
    fetch_cmd = commands.add_parser("fetch")
    fetch_cmd.add_argument("url")
    fetch_cmd.add_argument("--max-chars", type=int, default=DEFAULT_FETCH_CHARS)
    fetch_cmd.add_argument("--offset", type=int, default=0, help="start here; the last reply's next_offset")
    evidence = commands.add_parser("evidence").add_subparsers(dest="action", required=True)
    evidence_add = evidence.add_parser("add")
    evidence_add.add_argument("--story", required=True)
    evidence_add.add_argument("--json")
    lint = commands.add_parser("lint")
    lint.add_argument("file", type=Path)
    lint.add_argument("--surface", default="newsletter", choices=("newsletter", "social", "engagement", "site"))
    tells_cmd = commands.add_parser("tells")
    tells_cmd.add_argument("--since", type=int, default=30, help="days back")
    tells_cmd.add_argument("--surface", default="newsletter")
    tells_cmd.add_argument("--reports", type=Path, help="issue folder (default reports/<user>)")
    args = parser.parse_args(argv)

    def payload(text: str | None):
        raw = text if text is not None else sys.stdin.read()
        if text is None and not raw.lstrip().startswith("{"):
            return parse_fields(raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise Rejected([f"not valid JSON: {exc}"]) from exc

    try:
        if args.command == "finding":
            agent = os.environ.get("MINDPATTERN_AGENT") or "unknown"
            return _out(add_finding(payload(args.json), store=_env_path("MP_FINDINGS_FILE"), agent=agent))
        if args.command == "findings":
            rows = read_findings(_env_path("MP_FINDINGS_FILE"))
            return _out({"count": len(rows), "findings": [{"title": r.get("title"), "source_url": r.get("source_url"),
                                                           "importance": r.get("importance")} for r in rows]})
        if args.command == "seen":
            matches = history(args.query)
            return _out({"seen": bool(matches), "matches": matches})
        if args.command == "fetch":
            return _out(fetch(args.url, max_chars=args.max_chars, offset=args.offset))
        if args.command == "evidence":
            return _out(add_evidence(payload(args.json), story=args.story, store=_env_path("MP_EVIDENCE_FILE")))
        if args.command == "lint":
            from orchestrator import word_bank

            found = word_bank.violations(args.file.read_text(), args.surface)
            return _out({"clean": not found, "violations": found}, 0 if not found else 2)
        reports = args.reports or PROJECT_ROOT / "reports" / _user()
        return _out(tells(since_days=args.since, surface=args.surface, reports=reports))
    except Rejected as exc:
        return _out({"accepted": False, "reasons": exc.reasons}, 2)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _out({"ok": False, "error": str(exc)}, 1)
