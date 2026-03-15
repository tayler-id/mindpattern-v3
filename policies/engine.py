"""
Deterministic policy enforcement for MindPattern agents.

Code-enforced rules that cannot be gamed by prompt injection.
All validation is structural/deterministic — no LLM in the loop.
"""

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from memory.social import recent_posts

try:
    import unicodedata

    def count_graphemes(text: str) -> int:
        """Count user-perceived characters (grapheme clusters) in text."""
        count = 0
        i = 0
        while i < len(text):
            count += 1
            # Skip over combining characters and zero-width joiners
            i += 1
            while i < len(text) and unicodedata.category(text[i]).startswith(("M", "Sk")):
                i += 1
        return count

except ImportError:
    def count_graphemes(text: str) -> int:
        """Fallback: approximate grapheme count with len()."""
        return len(text)


class PolicyEngine:
    """Enforces deterministic policy rules loaded from JSON config files."""

    def __init__(self, policy_file: str | Path):
        """Load JSON policy rules from the given file.

        Args:
            policy_file: Path to a JSON policy file (research.json or social.json).
        """
        policy_path = Path(policy_file)
        if not policy_path.exists():
            raise FileNotFoundError(f"Policy file not found: {policy_path}")
        with open(policy_path, "r") as f:
            self.rules = json.load(f)

    @classmethod
    def load_research(cls, policy_dir: str | Path = None) -> "PolicyEngine":
        """Convenience: load research.json from the policies directory."""
        if policy_dir is None:
            policy_dir = Path(__file__).parent
        return cls(Path(policy_dir) / "research.json")

    @classmethod
    def load_social(cls, policy_dir: str | Path = None) -> "PolicyEngine":
        """Convenience: load social.json from the policies directory."""
        if policy_dir is None:
            policy_dir = Path(__file__).parent
        return cls(Path(policy_dir) / "social.json")

    # ── Research validation ──────────────────────────────────────────

    def validate_agent_output(self, agent_name: str, output: dict) -> list[str]:
        """Check findings against research.json rules.

        Args:
            agent_name: Name of the agent that produced the output.
            output: Dict with a "findings" key containing a list of finding dicts.

        Returns:
            List of error strings. Empty list means valid.
        """
        errors = []
        required_fields = self.rules.get("required_fields", [])
        valid_importance = self.rules.get("importance_values", [])
        max_findings = self.rules.get("max_findings_per_agent", 15)
        min_findings = self.rules.get("min_findings_per_agent", 1)
        max_summary_length = self.rules.get("max_summary_length", 1000)
        injection_patterns = self.rules.get("injection_patterns", [])

        findings = output.get("findings", [])

        # Validate findings count
        if len(findings) < min_findings:
            errors.append(
                f"[{agent_name}] Too few findings: {len(findings)} "
                f"(minimum {min_findings})"
            )
        if len(findings) > max_findings:
            errors.append(
                f"[{agent_name}] Too many findings: {len(findings)} "
                f"(maximum {max_findings})"
            )

        for i, finding in enumerate(findings):
            prefix = f"[{agent_name}] Finding {i + 1}"

            # Required fields
            for field in required_fields:
                if field not in finding or not finding[field]:
                    errors.append(f"{prefix}: missing required field '{field}'")

            # Source URL validation
            source_url = finding.get("source_url", "")
            if source_url:
                parsed = urlparse(source_url)
                if not parsed.scheme or not parsed.netloc:
                    errors.append(
                        f"{prefix}: invalid source_url '{source_url}' "
                        f"(must have scheme and netloc)"
                    )
                if parsed.scheme not in ("http", "https"):
                    errors.append(
                        f"{prefix}: source_url scheme must be http or https, "
                        f"got '{parsed.scheme}'"
                    )

            # Importance validation
            importance = finding.get("importance", "")
            if importance and importance not in valid_importance:
                errors.append(
                    f"{prefix}: invalid importance '{importance}' "
                    f"(must be one of {valid_importance})"
                )

            # Summary length
            summary = finding.get("summary", "")
            if summary and len(summary) > max_summary_length:
                errors.append(
                    f"{prefix}: summary too long ({len(summary)} chars, "
                    f"max {max_summary_length})"
                )

            # Prompt injection scan on all text fields
            text_fields = ["title", "summary", "source_name"]
            for field in text_fields:
                value = finding.get(field, "")
                if value:
                    injections = self.scan_for_injection(
                        value, patterns=injection_patterns
                    )
                    for pattern in injections:
                        errors.append(
                            f"{prefix}: prompt injection detected in '{field}': "
                            f"matched pattern '{pattern}'"
                        )

        return errors

    # ── Social post validation ───────────────────────────────────────

    def validate_social_post(self, platform: str, content: str) -> list[str]:
        """Check a social media post against social.json rules.

        Args:
            platform: Platform name (x, bluesky, linkedin).
            content: The post content text.

        Returns:
            List of error strings. Empty list means valid.
        """
        errors = []
        platforms = self.rules.get("platforms", {})
        banned_words = self.rules.get("banned_words", [])
        banned_patterns = self.rules.get("banned_patterns", [])

        # Platform existence check
        if platform not in platforms:
            errors.append(
                f"Unknown platform '{platform}' "
                f"(valid: {list(platforms.keys())})"
            )
            return errors

        platform_rules = platforms[platform]

        # Character / grapheme limits
        if "max_chars" in platform_rules:
            char_count = len(content)
            max_chars = platform_rules["max_chars"]
            if char_count > max_chars:
                errors.append(
                    f"[{platform}] Post exceeds character limit: "
                    f"{char_count}/{max_chars}"
                )

        if "max_graphemes" in platform_rules:
            grapheme_count = count_graphemes(content)
            max_graphemes = platform_rules["max_graphemes"]
            if grapheme_count > max_graphemes:
                errors.append(
                    f"[{platform}] Post exceeds grapheme limit: "
                    f"{grapheme_count}/{max_graphemes}"
                )

        # Required URL check
        if platform_rules.get("require_url", False):
            # Look for http:// or https:// URLs anywhere in content
            if not re.search(r"https?://\S+", content):
                errors.append(
                    f"[{platform}] Post must contain a URL"
                )

        # Banned words (case-insensitive)
        content_lower = content.lower()
        for word in banned_words:
            if word.lower() in content_lower:
                errors.append(
                    f"[{platform}] Banned word detected: '{word}'"
                )

        # Banned patterns (regex)
        for pattern in banned_patterns:
            try:
                if re.search(pattern, content):
                    errors.append(
                        f"[{platform}] Banned pattern detected: '{pattern}'"
                    )
            except re.error:
                # If the pattern is a literal string (like em dash), do literal check
                if pattern in content:
                    errors.append(
                        f"[{platform}] Banned pattern detected: '{pattern}'"
                    )

        return errors

    # ── Post rate limit (social_posts table) ────────────────────────

    def validate_post_rate_limit(
        self, platform: str, db: sqlite3.Connection
    ) -> str | None:
        """Check if posting is allowed based on today's actual post history.

        Loads max_posts_per_day from social.json rate_limits, then queries
        memory.social.recent_posts(db, days=1, platform) to count how many
        posts with posted=1 exist for today.

        Args:
            platform: Platform name (x, bluesky, linkedin).
            db: SQLite database connection with a social_posts table.

        Returns:
            Error string if at or over the limit, None if within limit.
        """
        rate_limits = self.rules.get("rate_limits", {})

        if platform not in rate_limits:
            return (
                f"Unknown platform '{platform}' "
                f"(valid: {list(rate_limits.keys())})"
            )

        max_per_day = rate_limits[platform].get("max_posts_per_day", 3)

        posts_today = recent_posts(db, days=1, platform=platform, limit=max_per_day + 10)
        posted_count = sum(1 for p in posts_today if p.get("posted"))

        if posted_count >= max_per_day:
            return (
                f"Post limit reached for {platform}: "
                f"{posted_count}/{max_per_day} today"
            )

        return None

    # ── Rate limit validation (engagements table) ─────────────────

    def validate_rate_limits(
        self, db: sqlite3.Connection, platform: str, action_type: str
    ) -> dict:
        """Check engagement rate limits against actual DB counts.

        Args:
            db: SQLite database connection with an 'engagements' table.
            platform: Platform name (x, bluesky, linkedin).
            action_type: Type of action (post, follow, reply).

        Returns:
            Dict with keys: allowed (bool), reason (str), current (int), limit (int).
        """
        rate_limits = self.rules.get("rate_limits", {})
        reply_cooldown_days = self.rules.get("reply_cooldown_days", 7)

        if platform not in rate_limits:
            return {
                "allowed": False,
                "reason": f"Unknown platform '{platform}'",
                "current": 0,
                "limit": 0,
            }

        platform_limits = rate_limits[platform]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if action_type == "post":
            limit = platform_limits.get("max_posts_per_day", 3)
            current = self._count_actions_today(db, platform, "post", today)
            allowed = current < limit
            reason = "" if allowed else (
                f"Post limit reached for {platform}: {current}/{limit} today"
            )
            return {
                "allowed": allowed,
                "reason": reason,
                "current": current,
                "limit": limit,
            }

        elif action_type == "follow":
            limit = platform_limits.get("max_follows_per_day", 50)
            current = self._count_actions_today(db, platform, "follow", today)
            allowed = current < limit
            reason = "" if allowed else (
                f"Follow limit reached for {platform}: {current}/{limit} today"
            )
            return {
                "allowed": allowed,
                "reason": reason,
                "current": current,
                "limit": limit,
            }

        elif action_type == "reply":
            limit = reply_cooldown_days
            # Check the most recent reply on this platform
            last_reply = self._last_action_date(db, platform, "reply")
            if last_reply:
                days_since = (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(last_reply).replace(tzinfo=timezone.utc)
                ).days
                allowed = days_since >= reply_cooldown_days
                reason = "" if allowed else (
                    f"Reply cooldown active for {platform}: "
                    f"{days_since}/{reply_cooldown_days} days since last reply"
                )
                return {
                    "allowed": allowed,
                    "reason": reason,
                    "current": days_since,
                    "limit": reply_cooldown_days,
                }
            else:
                # No previous replies — allowed
                return {
                    "allowed": True,
                    "reason": "",
                    "current": 0,
                    "limit": reply_cooldown_days,
                }

        else:
            return {
                "allowed": False,
                "reason": f"Unknown action type '{action_type}'",
                "current": 0,
                "limit": 0,
            }

    # ── Freshness check ──────────────────────────────────────────────

    def validate_finding_freshness(
        self, date_found: str, max_age_hours: int = None
    ) -> bool:
        """Check if a finding is recent enough.

        Args:
            date_found: ISO 8601 date/datetime string of when the finding was discovered.
            max_age_hours: Maximum age in hours. Defaults to policy value or 48.

        Returns:
            True if the finding is fresh enough, False otherwise.
        """
        if max_age_hours is None:
            max_age_hours = self.rules.get("max_age_hours", 48)

        try:
            found_dt = datetime.fromisoformat(date_found)
            if found_dt.tzinfo is None:
                found_dt = found_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return False

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        return found_dt >= cutoff

    # ── Injection scanner ────────────────────────────────────────────

    def scan_for_injection(
        self, text: str, patterns: list[str] = None
    ) -> list[str]:
        """Scan text for prompt injection patterns.

        Args:
            text: The text to scan.
            patterns: List of injection pattern strings to check.
                      Defaults to the policy file's injection_patterns.

        Returns:
            List of matched pattern strings. Empty means clean.
        """
        if patterns is None:
            patterns = self.rules.get("injection_patterns", [])

        detected = []
        text_lower = text.lower()

        for pattern in patterns:
            if pattern.lower() in text_lower:
                detected.append(pattern)

        return detected

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _count_actions_today(
        db: sqlite3.Connection, platform: str, action_type: str, today: str
    ) -> int:
        """Count how many actions of a type were performed today on a platform."""
        try:
            cursor = db.execute(
                """
                SELECT COUNT(*) FROM engagements
                WHERE platform = ? AND action_type = ?
                AND date(created_at) = ?
                """,
                (platform, action_type, today),
            )
            return cursor.fetchone()[0]
        except sqlite3.OperationalError:
            # Table might not exist yet
            return 0

    @staticmethod
    def _last_action_date(
        db: sqlite3.Connection, platform: str, action_type: str
    ) -> str | None:
        """Get the ISO date string of the most recent action of a type."""
        try:
            cursor = db.execute(
                """
                SELECT created_at FROM engagements
                WHERE platform = ? AND action_type = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (platform, action_type),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.OperationalError:
            return None
