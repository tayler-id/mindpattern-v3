"""Preflight: Exa semantic search via mcporter."""

import logging
import re
import subprocess

from . import make_entry

logger = logging.getLogger(__name__)

DEFAULT_QUERIES = [
    "AI agent framework launch 2026",
    "LLM benchmark results latest",
    "AI coding assistant update",
    "SaaS AI disruption startup",
    "fintech AI automation",
]


def _parse_mcporter_output(text: str) -> list[dict]:
    results = []
    blocks = re.split(r"(?=^Title: )", text, flags=re.MULTILINE)

    for block in blocks:
        block = block.strip()
        if not block.startswith("Title: "):
            continue

        title_m = re.match(r"Title: (.+)", block)
        url_m = re.search(r"^URL: (.+)", block, re.MULTILINE)
        date_m = re.search(r"^Published Date: (.+)", block, re.MULTILINE)
        author_m = re.search(r"^Author: (.+)", block, re.MULTILINE)
        text_m = re.search(r"^Text: (.+)", block, re.MULTILINE | re.DOTALL)

        if not title_m or not url_m:
            continue

        published = ""
        if date_m:
            raw_date = date_m.group(1).strip()
            pub_match = re.match(r"(\d{4}-\d{2}-\d{2})", raw_date)
            published = pub_match.group(1) + "T00:00:00Z" if pub_match else raw_date

        content = text_m.group(1).strip()[:500] if text_m else ""
        source_name = author_m.group(1).strip() if author_m else "Exa"

        results.append({
            "title": title_m.group(1).strip(),
            "url": url_m.group(1).strip(),
            "published": published,
            "content": content,
            "source_name": source_name,
        })

    return results


def fetch(queries: list[str] | None = None, num_results: int = 5) -> list[dict]:
    queries = queries or DEFAULT_QUERIES
    all_items = []
    seen_urls = set()

    for query in queries:
        cmd = [
            "mcporter", "call", "exa.web_search_exa",
            f"query={query}", f"numResults={num_results}",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                logger.warning(f"mcporter exa failed for '{query}': {proc.stderr[:200]}")
                continue

            results = _parse_mcporter_output(proc.stdout)
            for r in results:
                if r["url"] in seen_urls:
                    continue
                seen_urls.add(r["url"])
                all_items.append(make_entry(
                    source="exa",
                    source_name=r.get("source_name", "Exa"),
                    title=r["title"],
                    url=r["url"],
                    published=r.get("published", ""),
                    content_preview=r.get("content", ""),
                ))

        except subprocess.TimeoutExpired:
            logger.warning(f"mcporter timed out for '{query}'")
        except FileNotFoundError:
            logger.error("mcporter not found")
            return []
        except Exception as e:
            logger.error(f"mcporter failed for '{query}': {e}")

    return all_items
