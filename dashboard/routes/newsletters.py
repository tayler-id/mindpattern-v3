"""Newsletters Browser tab -- browse past daily newsletter markdown files."""

import re
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

# Possible report directories (v3 production via symlink, v3 local, v2 local)
_REPORT_DIRS = [
    Path(__file__).parent.parent.parent / "data" / "reports" / "ramsay",  # /app/data/reports/ramsay -> /data/reports/ramsay on Fly.io
    Path(__file__).parent.parent.parent / "reports" / "ramsay",
    Path("/Users/taylerramsay/Projects/daily-research-agent/reports/ramsay"),
]


def _get_reports_dir() -> Optional[Path]:
    """Return the first existing reports directory."""
    for d in _REPORT_DIRS:
        if d.is_dir():
            return d
    return None


def _is_newsletter_file(p: Path) -> bool:
    """Return True if the file matches YYYY-MM-DD.md (no suffixes like -health)."""
    return bool(_DATE_RE.match(p.stem))


def _extract_title(filepath: Path) -> str:
    """Extract the title from the first heading line of a markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
                if line:
                    # First non-empty line that isn't a heading
                    return line[:100]
        return "Untitled"
    except Exception:
        return "Untitled"


def _get_newsletter_list() -> List[dict]:
    """Return list of newsletter metadata dicts sorted by date descending."""
    reports_dir = _get_reports_dir()
    if reports_dir is None:
        return []

    newsletters = []
    for p in reports_dir.glob("*.md"):
        if not _is_newsletter_file(p):
            continue
        date_str = p.stem
        title = _extract_title(p)
        try:
            size_bytes = p.stat().st_size
            if size_bytes >= 1024:
                size_display = f"{size_bytes / 1024:.1f} KB"
            else:
                size_display = f"{size_bytes} B"
        except Exception:
            size_display = "---"

        newsletters.append({
            "date": date_str,
            "title": title,
            "size": size_display,
            "path": str(p),
        })

    newsletters.sort(key=lambda x: x["date"], reverse=True)
    return newsletters


def _render_markdown(text: str) -> str:
    """Render markdown to HTML, with fallback to <pre> if markdown lib unavailable."""
    try:
        import markdown
        return markdown.markdown(
            text,
            extensions=["tables", "fenced_code", "toc", "nl2br"],
        )
    except ImportError:
        # Fallback: wrap in <pre> with basic escaping
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"<pre style='white-space:pre-wrap;color:#cbd5e1;'>{escaped}</pre>"


# -- Detail route (must be before the list route to avoid path conflict) ------


@router.get("/newsletters/{date}", response_class=HTMLResponse)
def newsletter_detail(request: Request, date: str):
    """Return detail view for a single newsletter."""
    is_htmx = request.headers.get("HX-Request") == "true"

    # Validate date format
    if not _DATE_RE.match(date):
        ctx = {
            "request": request,
            "newsletter_date": date,
            "newsletter_html": None,
            "newsletter_title": None,
        }
        if is_htmx:
            return templates.TemplateResponse("tabs/newsletter_detail.html", ctx)
        return templates.TemplateResponse("base.html", {
            **ctx,
            "active_tab": "newsletters",
            "tab_template": "tabs/newsletter_detail.html",
        })

    reports_dir = _get_reports_dir()
    newsletter_html = None
    newsletter_title = None

    if reports_dir:
        filepath = reports_dir / f"{date}.md"
        if filepath.exists():
            try:
                raw = filepath.read_text(encoding="utf-8")
                newsletter_html = _render_markdown(raw)
                newsletter_title = _extract_title(filepath)
            except Exception:
                newsletter_html = None

    ctx = {
        "request": request,
        "newsletter_date": date,
        "newsletter_html": newsletter_html,
        "newsletter_title": newsletter_title,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/newsletter_detail.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "newsletters",
        "tab_template": "tabs/newsletter_detail.html",
    })


# -- Main list route ----------------------------------------------------------


@router.get("/newsletters", response_class=HTMLResponse)
def newsletters_list(request: Request):
    """Return newsletters browser with list of all past newsletters."""
    newsletters = _get_newsletter_list()

    # Summary stats
    date_min = newsletters[-1]["date"] if newsletters else ""
    date_max = newsletters[0]["date"] if newsletters else ""

    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "newsletters": newsletters,
        "total_count": len(newsletters),
        "date_min": date_min,
        "date_max": date_max,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/newsletters.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "newsletters",
        "tab_template": "tabs/newsletters.html",
    })
