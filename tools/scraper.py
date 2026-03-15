"""Adaptive web scraper for sources with broken RSS feeds.

Uses Scrapling for resilient scraping that survives site redesigns.
Falls back gracefully if Scrapling is not installed.

Usage:
    from tools.scraper import scrape_source, check_rss_health

    articles = scrape_source("https://blog.example.com")
    health = check_rss_health("https://blog.example.com/feed")
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

# Common date patterns found on blog posts and news articles
_DATE_PATTERNS = [
    # ISO-8601 variants
    (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "%Y-%m-%dT%H:%M:%S"),
    (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
    # US-style: March 14, 2026 / Mar 14, 2026
    (
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}",
        None,  # handled by _parse_human_date
    ),
    # DD/MM/YYYY and MM/DD/YYYY (ambiguous — assume US)
    (r"\d{1,2}/\d{1,2}/\d{4}", "%m/%d/%Y"),
    # DD Mon YYYY: 14 Mar 2026
    (r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}", "%d %b %Y"),
]

_HUMAN_MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def scrape_source(url: str, *, timeout: int = 20) -> list[dict]:
    """Scrape a web page for articles/posts.

    Uses Scrapling's adaptive parser. Falls back to basic requests+html parsing
    if Scrapling not installed.

    Args:
        url: The page URL to scrape for article links and metadata.
        timeout: Request timeout in seconds.

    Returns:
        List of dicts, each with keys: title, content, url, date, author.
        Empty list on total failure.
    """
    try:
        return _scrape_with_scrapling(url, timeout=timeout)
    except ImportError:
        logger.info("Scrapling not installed, using fallback scraper for %s", url)
        return _scrape_fallback(url, timeout=timeout)
    except Exception as exc:
        logger.warning("Scrapling scrape failed for %s: %s — trying fallback", url, exc)
        try:
            return _scrape_fallback(url, timeout=timeout)
        except Exception as fallback_exc:
            logger.error("Both scrapers failed for %s: %s", url, fallback_exc)
            return []


def check_rss_health(feed_url: str, *, timeout: int = 15) -> dict:
    """Check if an RSS feed is healthy.

    Fetches the feed with feedparser and checks for valid entries, parsability,
    and recency of the most recent item.

    Args:
        feed_url: URL of the RSS/Atom feed.
        timeout: Request timeout in seconds (passed to feedparser's underlying fetch).

    Returns:
        Dict with keys:
            healthy (bool): True if the feed has valid, recent entries.
            items_count (int): Number of items found.
            last_updated (str): ISO date of the most recent item, or empty string.
            error (str): Error message if unhealthy, empty string otherwise.
    """
    try:
        import feedparser
    except ImportError:
        return {
            "healthy": False,
            "items_count": 0,
            "last_updated": "",
            "error": "feedparser not installed",
        }

    try:
        feed = feedparser.parse(feed_url)
    except Exception as exc:
        return {
            "healthy": False,
            "items_count": 0,
            "last_updated": "",
            "error": f"Parse error: {exc}",
        }

    # Check for bozo (malformed feed)
    if feed.get("bozo") and not feed.get("entries"):
        exc = feed.get("bozo_exception", "Unknown parse error")
        return {
            "healthy": False,
            "items_count": 0,
            "last_updated": "",
            "error": f"Malformed feed: {exc}",
        }

    entries = feed.get("entries", [])
    items_count = len(entries)

    if items_count == 0:
        return {
            "healthy": False,
            "items_count": 0,
            "last_updated": "",
            "error": "Feed contains no entries",
        }

    # Find the most recent entry date
    last_updated = ""
    most_recent_dt = None

    for entry in entries:
        pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub_struct:
            try:
                import calendar
                ts = calendar.timegm(pub_struct)
                dt = datetime.utcfromtimestamp(ts)
                if most_recent_dt is None or dt > most_recent_dt:
                    most_recent_dt = dt
            except (ValueError, OverflowError, OSError):
                continue

    if most_recent_dt:
        last_updated = most_recent_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # A feed is healthy if it has entries and at least some have dates
    # If the most recent item is older than 90 days, consider it stale
    healthy = True
    error = ""

    if most_recent_dt:
        age_days = (datetime.utcnow() - most_recent_dt).days
        if age_days > 90:
            healthy = False
            error = f"Feed is stale: most recent entry is {age_days} days old"
    else:
        # No parseable dates at all — might still be usable but flag it
        error = "No parseable dates in feed entries"

    return {
        "healthy": healthy,
        "items_count": items_count,
        "last_updated": last_updated,
        "error": error,
    }


def extract_date(text: str) -> str | None:
    """Extract a date from text using common patterns.

    Tries ISO-8601, human-readable (March 14, 2026), and numeric formats.

    Args:
        text: Text that may contain a date.

    Returns:
        ISO date string (YYYY-MM-DD) or None if no date found.
    """
    if not text:
        return None

    for pattern, fmt in _DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(0)
            if fmt:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            else:
                # Human-readable month name format
                parsed = _parse_human_date(date_str)
                if parsed:
                    return parsed

    return None


def _parse_human_date(text: str) -> str | None:
    """Parse dates like 'March 14, 2026' or 'Mar 14 2026'.

    Args:
        text: Date string with month name.

    Returns:
        ISO date string (YYYY-MM-DD) or None.
    """
    # Remove commas and extra spaces
    cleaned = re.sub(r",", "", text).strip()
    parts = cleaned.split()

    if len(parts) < 3:
        return None

    month_str = parts[0].lower()
    month = _HUMAN_MONTH_MAP.get(month_str)
    if month is None:
        return None

    try:
        day = int(parts[1])
        year = int(parts[2])
    except (ValueError, IndexError):
        return None

    try:
        dt = datetime(year, month, day)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def _scrape_with_scrapling(url: str, *, timeout: int = 20) -> list[dict]:
    """Scrapling-based scraping (preferred).

    Uses Scrapling's Adaptor for resilient CSS-based extraction that survives
    minor site redesigns. Extracts article links from a listing page.

    Args:
        url: Page URL to scrape.
        timeout: Request timeout in seconds.

    Returns:
        List of article dicts: {title, content, url, date, author}.
    """
    from scrapling import Adaptor
    import requests

    resp = requests.get(url, timeout=timeout, headers={
        "User-Agent": "MindPattern/3.0 (research-agent; +https://mindpattern.ai)",
        "Accept": "text/html,application/xhtml+xml",
    })
    resp.raise_for_status()

    page = Adaptor(resp.text, url=url)
    articles = []

    # Strategy 1: Look for <article> elements
    article_elements = page.css("article")

    if article_elements:
        for article_el in article_elements:
            article = _extract_article_from_element(article_el, url)
            if article and article["title"]:
                articles.append(article)
    else:
        # Strategy 2: Look for common blog post listing patterns
        # Try h2 > a or h3 > a (common blog patterns)
        for selector in ["h2 a", "h3 a", ".post-title a", ".entry-title a",
                         "[class*='title'] a", "[class*='post'] a[href]"]:
            link_elements = page.css(selector)
            if link_elements:
                for link_el in link_elements:
                    href = link_el.attrib.get("href", "")
                    title = link_el.text.strip() if link_el.text else ""

                    if not href or not title:
                        continue

                    full_url = urljoin(url, href)

                    # Walk up to the parent container for date/author
                    parent = link_el.parent
                    date = None
                    author = None

                    if parent is not None:
                        parent_text = parent.text or ""
                        date = extract_date(parent_text)

                        # Look for author-like patterns in parent
                        author_match = re.search(
                            r"(?:by|author)[:\s]+([A-Z][a-z]+(?: [A-Z][a-z]+)*)",
                            parent_text, re.IGNORECASE,
                        )
                        if author_match:
                            author = author_match.group(1)

                    articles.append({
                        "title": title,
                        "content": "",
                        "url": full_url,
                        "date": date or "",
                        "author": author or "",
                    })

                if articles:
                    break  # stop trying selectors once we find matches

    logger.info("Scrapling found %d articles at %s", len(articles), url)
    return articles


def _extract_article_from_element(article_el, base_url: str) -> dict | None:
    """Extract article metadata from a Scrapling <article> element.

    Args:
        article_el: A Scrapling Adaptor element representing an <article>.
        base_url: Base URL for resolving relative links.

    Returns:
        Dict with title, content, url, date, author. None if no link found.
    """
    # Find the primary link
    link_el = (
        article_el.css("h2 a") or article_el.css("h3 a") or
        article_el.css("a[class*='title']") or article_el.css("a")
    )

    if not link_el:
        return None

    first_link = link_el[0]
    href = first_link.attrib.get("href", "")
    title = first_link.text.strip() if first_link.text else ""

    if not href:
        return None

    full_url = urljoin(base_url, href)

    # Extract date from time element or text content
    time_el = article_el.css("time")
    date = ""
    if time_el:
        date = time_el[0].attrib.get("datetime", "")
        if date:
            date = date[:10]  # Trim to YYYY-MM-DD
        else:
            date = extract_date(time_el[0].text or "") or ""
    else:
        # Try extracting from the article text
        article_text = article_el.text or ""
        date = extract_date(article_text) or ""

    # Extract author
    author = ""
    author_el = (
        article_el.css("[class*='author']") or
        article_el.css("[rel='author']") or
        article_el.css(".byline")
    )
    if author_el:
        author = (author_el[0].text or "").strip()

    # Extract summary/content snippet
    content = ""
    summary_el = (
        article_el.css("p") or
        article_el.css("[class*='excerpt']") or
        article_el.css("[class*='summary']")
    )
    if summary_el:
        content = (summary_el[0].text or "").strip()[:300]

    return {
        "title": title,
        "content": content,
        "url": full_url,
        "date": date,
        "author": author,
    }


def _scrape_fallback(url: str, *, timeout: int = 20) -> list[dict]:
    """Basic requests + regex scraping (fallback).

    Extracts links from <a> tags using regex when neither Scrapling nor
    a proper HTML parser is available. Filters to likely article links
    based on URL path patterns.

    Args:
        url: Page URL to scrape.
        timeout: Request timeout in seconds.

    Returns:
        List of article dicts: {title, content, url, date, author}.
    """
    import requests

    resp = requests.get(url, timeout=timeout, headers={
        "User-Agent": "MindPattern/3.0 (research-agent; +https://mindpattern.ai)",
        "Accept": "text/html,application/xhtml+xml",
    })
    resp.raise_for_status()
    html = resp.text

    # Extract all links with text
    link_pattern = re.compile(
        r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    parsed_url = urlparse(url)
    base_domain = parsed_url.netloc

    # Patterns that suggest an article URL (not navigation)
    article_path_patterns = re.compile(
        r"/(?:blog|post|article|news|story|20\d{2})/",
        re.IGNORECASE,
    )

    articles = []
    seen_urls = set()

    for href, raw_title in link_pattern.findall(html):
        # Clean title of HTML tags
        title = re.sub(r"<[^>]+>", "", raw_title).strip()

        if not title or len(title) < 10:
            continue

        # Skip navigation links (short, generic text)
        if title.lower() in {"home", "about", "contact", "search", "menu",
                              "login", "sign up", "subscribe", "read more",
                              "learn more", "click here"}:
            continue

        full_url = urljoin(url, href)
        link_parsed = urlparse(full_url)

        # Only follow links on the same domain or common CDN patterns
        if link_parsed.netloc and link_parsed.netloc != base_domain:
            continue

        # Skip anchors, javascript, and non-http links
        if href.startswith(("#", "javascript:", "mailto:")):
            continue

        # Prefer links that look like article paths
        if not article_path_patterns.search(full_url):
            # Still include if the path is reasonably deep (not just /)
            if link_parsed.path.count("/") < 2:
                continue

        # Dedup by URL
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Try to extract a date from nearby HTML context
        # Look for the link in the original HTML and grab surrounding text
        date = ""
        link_pos = html.find(href)
        if link_pos > 0:
            context_start = max(0, link_pos - 500)
            context_end = min(len(html), link_pos + 500)
            context = html[context_start:context_end]
            # Strip HTML for date extraction
            context_clean = re.sub(r"<[^>]+>", " ", context)
            date = extract_date(context_clean) or ""

        articles.append({
            "title": title,
            "content": "",
            "url": full_url,
            "date": date,
            "author": "",
        })

    logger.info("Fallback scraper found %d articles at %s", len(articles), url)
    return articles
