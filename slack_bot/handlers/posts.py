"""#mp-posts handler: idea or URL → full social post pipeline → approve → publish.

Drop a URL or text idea in #mp-posts and the bot will:
1. Frame the topic (Creative Director agent)
2. Run writers (per-platform agents with voice guide)
3. Run critics (blind validation agents)
4. Run humanizer (AI pattern removal agent)
5. Run expeditor (final quality gate agent)
6. Post drafts back in a thread
7. Wait for approval (ALL / BLUESKY / LINKEDIN / SKIP)
8. Post to platforms

Uses the same agent files and pipeline modules as the daily social pipeline.
"""

import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from slack_bot.handlers.base import BaseHandler

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

# Add project root to path so we can import pipeline modules
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class PostsHandler(BaseHandler):
    """Handle messages in #mp-posts — idea or URL to social post pipeline."""

    def handle(self, event: dict) -> None:
        """Process a message in #mp-posts."""
        text = event.get("text", "").strip()
        ts = event.get("ts", "")

        if not text:
            return

        if text.lower() in ("help", "?"):
            self.reply(
                "Drop a URL or a text idea here and I'll create social posts from it.\n"
                "I'll run the full agent pipeline "
                "(Creative Director → writers → critics → humanizer → expeditor), "
                "then post drafts back for your approval.",
                thread_ts=ts,
            )
            return

        # Extract URLs from the message
        urls = self.extract_urls(text)

        if urls:
            url = urls[0]
            if not self.is_valid_url(url):
                self.reply(f"That doesn't look like a valid URL: {url}", thread_ts=ts)
                return
            self._handle_url(url, text, ts)
        else:
            self._handle_idea(text, ts)

    def _handle_url(self, url: str, text: str, ts: str) -> None:
        """Handle a URL post — read article, then run pipeline."""
        self.react("eyes", ts)
        self.reply("Reading article...", thread_ts=ts)

        content = self.read_url(url)
        if not content:
            self.reply("Couldn't read that URL. It might be paywalled or down.", thread_ts=ts)
            return

        title = content.split("\n")[0][:200] if content else "Untitled"
        article_text = content[:8000]

        # Build a topic dict that matches what the daily pipeline produces
        topic = {
            "anchor": f"{title}. {article_text[:500]}",
            "anchor_source": f"{title} - {url}",
            "connection": "",
            "connection_source": "",
            "reaction": text if text != url else "",
            "source_urls": [url],
            "confidence": "HIGH",
        }

        self.reply(
            f"Got it: *{title}*\nRunning pipeline (Creative Director → writers → critics → humanizer → expeditor)...",
            thread_ts=ts,
        )
        self._run_and_approve(topic, ts)

    def _handle_idea(self, idea: str, ts: str) -> None:
        """Handle a text idea — use the idea directly as the topic."""
        self.react("eyes", ts)
        self.reply("Running pipeline on your idea...", thread_ts=ts)

        topic = {
            "anchor": idea,
            "anchor_source": "",
            "connection": "",
            "connection_source": "",
            "reaction": idea,
            "source_urls": [],
            "confidence": "HIGH",
        }

        self._run_and_approve(topic, ts)

    def _run_and_approve(self, topic: dict, ts: str) -> None:
        """Run the full social pipeline and handle approval flow."""
        try:
            drafts = self._run_social_pipeline(topic)
        except Exception as e:
            logger.error(f"[mp-posts] Pipeline failed: {e}", exc_info=True)
            self.reply(f"Pipeline failed: {e}", thread_ts=ts)
            return

        if not drafts:
            self.reply("The pipeline didn't produce any drafts.", thread_ts=ts)
            return

        # Warn about missing platforms
        expected = {"bluesky", "linkedin"}
        missing = expected - set(drafts.keys())
        if missing:
            self.reply(
                f":warning: Failed to generate drafts for: {', '.join(missing)}. "
                f"Proceeding with {', '.join(drafts.keys())} only.",
                thread_ts=ts,
            )

        # Post drafts for approval
        draft_msg = self._format_drafts(drafts)
        self.reply(draft_msg, thread_ts=ts)

        # Wait for approval
        reply_text = self.wait_for_reply(ts)
        if not reply_text:
            self.reply("No response — cancelling.", thread_ts=ts)
            return

        approved_platforms = self._parse_approval(reply_text, list(drafts.keys()))
        if not approved_platforms:
            self.reply("Skipped. Nothing posted.", thread_ts=ts)
            return

        # Post to platforms
        self.reply(f"Posting to: {', '.join(approved_platforms)}...", thread_ts=ts)
        results = self._post_to_platforms(drafts, approved_platforms)

        # Report results
        result_lines = []
        for platform, result in results.items():
            if result.get("success"):
                result_lines.append(f":white_check_mark: {platform}: {result.get('url', 'posted')}")
            else:
                result_lines.append(f":x: {platform}: {result.get('error', 'unknown')}")

        self.reply("\n".join(result_lines), thread_ts=ts)

    def _run_social_pipeline(self, topic: dict) -> dict:
        """Run the full social pipeline using the same agents as the daily pipeline.

        Steps: Creative Director → writers → critics → humanizer → expeditor
        All use the real agent .md files and voice/soul/user identity.

        Returns: {platform: draft_text} dict
        """
        from social.eic import create_brief
        from social.writers import write_drafts
        from social.critics import expedite

        date_str = datetime.now().strftime("%Y-%m-%d")
        config = self._load_social_config()
        db_path = PROJECT_ROOT / "data" / "ramsay" / "memory.db"
        db = sqlite3.connect(str(db_path))

        try:
            # Step 1: Creative Director generates the brief
            logger.info(f"[mp-posts] Creative Director: generating brief")
            brief = create_brief(db, topic, date_str)
            if not brief:
                logger.warning("[mp-posts] Creative Director returned no brief, using fallback")
                brief = {
                    "editorial_angle": topic.get("anchor", ""),
                    "key_message": topic.get("reaction", ""),
                    "tone": "direct",
                    "emotional_register": "neutral",
                    "platform_hooks": {},
                    "source_urls": topic.get("source_urls", []),
                    "do_not_include": [],
                    "mindpattern_link": "https://mindpattern.ai",
                    "_eic_topic": topic,
                    "date": date_str,
                }
            logger.info(f"[mp-posts] Brief generated: {brief.get('editorial_angle', '')[:100]}")

            # Step 2-5: Writers + critics + humanizer (all handled by write_drafts)
            logger.info("[mp-posts] Running writers (writer → critic → policy → humanizer)")
            results = write_drafts(db, brief, config)
        finally:
            db.close()

        # Extract final draft text from results
        drafts = {}
        for platform, result in results.items():
            content = result.get("humanized") or result.get("content", "")
            if content and content.strip():
                drafts[platform] = content.strip()
                logger.info(
                    f"[mp-posts] {platform}: {len(content)} chars, "
                    f"iterations={result.get('iterations', 0)}, "
                    f"critic={result.get('critic_verdict', '?')}"
                )
            else:
                error = result.get("error", "empty output")
                logger.warning(f"[mp-posts] {platform} writer failed: {error}")

        if not drafts:
            return drafts

        # Step 6: Expeditor (final quality gate)
        logger.info("[mp-posts] Running expeditor")
        try:
            exp_result = expedite(drafts, brief, images={})
            if exp_result and exp_result.get("verdict", "").upper() == "FAIL":
                logger.warning(f"[mp-posts] Expeditor FAILED: {exp_result.get('feedback', '')}")
                # Don't remove drafts — let user see and decide
        except Exception as e:
            logger.warning(f"[mp-posts] Expeditor error (non-fatal): {e}")

        logger.info(f"[mp-posts] Pipeline complete: drafts for {list(drafts.keys())}")
        return drafts

    def _load_social_config(self) -> dict:
        """Load social-config.json from project root."""
        config_path = PROJECT_ROOT / "social-config.json"
        with open(config_path) as f:
            return json.load(f)

    def _format_drafts(self, drafts: dict) -> str:
        """Format drafts for Slack display."""
        lines = ["Here are your drafts:\n"]
        for platform, draft in drafts.items():
            char_count = len(draft)
            lines.append(f"*{platform.title()}* ({char_count} chars):")
            lines.append(f"```{draft}```")
            lines.append("")

        lines.append("Reply: *ALL* to post both, *BLUESKY* or *LINKEDIN* for one, *SKIP* to cancel.")
        lines.append("Or paste edited text to replace a draft.")
        return "\n".join(lines)

    def _parse_approval(self, reply: str, platforms: list[str]) -> list[str]:
        """Parse an approval reply into a list of platforms to post to."""
        reply_lower = reply.lower().strip()

        if reply_lower in ("skip", "no", "cancel", "n"):
            return []

        if reply_lower in ("all", "yes", "y", "go", "post"):
            return platforms

        # Check for specific platform names
        approved = []
        for p in platforms:
            if p.lower() in reply_lower:
                approved.append(p)
        return approved if approved else []

    def _post_to_platforms(self, drafts: dict, platforms: list[str]) -> dict:
        """Post drafts to approved platforms. Returns {platform: result}."""
        from social.posting import BlueskyClient, LinkedInClient

        config = self._load_social_config()
        results = {}
        for platform in platforms:
            draft = drafts.get(platform)
            if not draft:
                results[platform] = {"success": False, "error": "No draft for this platform"}
                continue

            try:
                if platform == "bluesky":
                    client = BlueskyClient(config["platforms"]["bluesky"])
                    post_result = client.post(draft)
                    results[platform] = {"success": True, "url": post_result.get("url", ""), "uri": post_result.get("uri", "")}
                elif platform == "linkedin":
                    client = LinkedInClient(config["platforms"]["linkedin"])
                    post_result = client.post(draft)
                    results[platform] = {"success": True, "url": post_result.get("url", "")}
                else:
                    results[platform] = {"success": False, "error": f"Unknown platform: {platform}"}
            except Exception as e:
                logger.error(f"[mp-posts] Failed to post to {platform}: {e}")
                results[platform] = {"success": False, "error": str(e)}

        return results
