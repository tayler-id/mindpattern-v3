"""#mp-posts handler: URL → full social post pipeline → approve → publish.

Drop a URL in #mp-posts and the bot will:
1. Read the article (Jina Reader)
2. Run EIC topic framing
3. Run writers (parallel for each platform)
4. Run critics (blind validation)
5. Run humanizer + expeditor
6. Post drafts back in a thread
7. Wait for approval (ALL / BLUESKY / LINKEDIN / SKIP)
8. Post to platforms
"""

import json
import logging
import os
import sys
from pathlib import Path

from slack_bot.handlers.base import BaseHandler

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

# Add project root to path so we can import pipeline modules
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class PostsHandler(BaseHandler):
    """Handle messages in #mp-posts — URL to social post pipeline."""

    def handle(self, event: dict) -> None:
        """Process a message in #mp-posts."""
        text = event.get("text", "").strip()
        ts = event.get("ts", "")

        # Extract URLs from the message
        urls = self.extract_urls(text)

        if not urls:
            # Not a URL — might be a command or question
            if text.lower() in ("help", "?"):
                self.reply(
                    "Drop a URL here and I'll create social posts from it.\n"
                    "I'll read the article, run the full agent pipeline "
                    "(EIC → writers → critics → humanizer), and post drafts "
                    "back for your approval.",
                    thread_ts=ts,
                )
            return

        url = urls[0]  # Process first URL
        if not self.is_valid_url(url):
            self.reply(f"That doesn't look like a valid URL: {url}", thread_ts=ts)
            return

        # Start the pipeline in a thread
        self.react("eyes", ts)
        self.reply(f"Reading article...", thread_ts=ts)

        # Step 1: Read the article
        content = self.read_url(url)
        if not content:
            self.reply("Couldn't read that URL. It might be paywalled or down.", thread_ts=ts)
            return

        # Truncate for LLM context
        title = content.split("\n")[0][:200] if content else "Untitled"
        article_text = content[:8000]

        self.reply(f"Got it: *{title}*\nDrafting social posts...", thread_ts=ts)

        # Step 2-6: Run the full agent pipeline
        try:
            drafts = self._run_social_pipeline(url, title, article_text)
        except Exception as e:
            logger.error(f"Pipeline failed for {url}: {e}", exc_info=True)
            self.reply(f"Pipeline failed: {e}", thread_ts=ts)
            return

        if not drafts:
            self.reply("The pipeline didn't produce any drafts. The article might not have enough substance.", thread_ts=ts)
            return

        # Step 7: Post drafts for approval
        draft_msg = self._format_drafts(drafts)
        self.reply(draft_msg, thread_ts=ts)

        # Step 8: Wait for approval
        reply_text = self.wait_for_reply(ts)
        if not reply_text:
            self.reply("No response — cancelling.", thread_ts=ts)
            return

        # Parse approval
        approved_platforms = self._parse_approval(reply_text, list(drafts.keys()))
        if not approved_platforms:
            self.reply("Skipped. Nothing posted.", thread_ts=ts)
            return

        # Step 9: Post to platforms
        self.reply(f"Posting to: {', '.join(approved_platforms)}...", thread_ts=ts)
        results = self._post_to_platforms(drafts, approved_platforms)

        # Report results
        result_lines = []
        for platform, result in results.items():
            if result.get("success"):
                result_lines.append(f"Posted to {platform}")
            else:
                result_lines.append(f"{platform} failed: {result.get('error', 'unknown')}")

        self.reply("\n".join(result_lines), thread_ts=ts)

    def _run_social_pipeline(self, url: str, title: str, article_text: str) -> dict:
        """Run the full social pipeline: EIC → writers → critics → humanizer.

        Returns: {platform: draft_text} dict
        """
        from orchestrator.agents import run_agent_with_files, run_claude_prompt
        from memory.vault import read_source_file

        vault_dir = PROJECT_ROOT / "data" / "ramsay" / "mindpattern"

        # Load identity files
        voice = read_source_file(vault_dir / "voice.md")
        soul = read_source_file(vault_dir / "soul.md")
        user = read_source_file(vault_dir / "user.md")

        # EIC: Frame the topic
        eic_prompt = (
            f"You are the Editor-in-Chief. A user wants to post about this article.\n\n"
            f"URL: {url}\n"
            f"Title: {title}\n\n"
            f"Article excerpt:\n{article_text[:3000]}\n\n"
            f"Identity:\n{soul[:500]}\n\n"
            f"Create a creative brief for social posts. Output JSON:\n"
            f'{{"topic": "...", "angle": "...", "key_insight": "...", "target_platforms": ["bluesky", "linkedin"]}}'
        )
        eic_output, _ = run_claude_prompt(eic_prompt, task_type="eic")

        # Parse EIC output
        try:
            brief = json.loads(eic_output) if eic_output else {}
        except json.JSONDecodeError:
            brief = {"topic": title, "angle": "Share key insight", "key_insight": article_text[:200]}

        topic = brief.get("topic", title)
        angle = brief.get("angle", "")
        insight = brief.get("key_insight", "")

        # Writers: Draft for each platform
        writer_prompt_base = (
            f"Write a social media post about this topic.\n\n"
            f"Topic: {topic}\nAngle: {angle}\nKey insight: {insight}\n"
            f"Source URL: {url}\n\n"
            f"Voice guide:\n{voice[:1000]}\n\n"
        )

        drafts = {}

        # Bluesky draft (300 chars max)
        bs_prompt = writer_prompt_base + (
            "Platform: Bluesky\n"
            "HARD LIMIT: 300 characters total including the URL.\n"
            "Include https://mindpattern.ai at end if space allows.\n"
            "Tone: conversational, lowercase fine, technically specific.\n"
            "Output ONLY the post text, nothing else."
        )
        bs_draft, _ = run_claude_prompt(bs_prompt, task_type="writer")
        if bs_draft:
            drafts["bluesky"] = bs_draft.strip()

        # LinkedIn draft (3000 chars max)
        li_prompt = writer_prompt_base + (
            "Platform: LinkedIn\n"
            "Target length: 800-1350 characters.\n"
            "Professional but not corporate. Share a real insight, not a summary.\n"
            "No hashtags. No emoji bullets. No 'I'm excited to announce' patterns.\n"
            "Output ONLY the post text, nothing else."
        )
        li_draft, _ = run_claude_prompt(li_prompt, task_type="writer")
        if li_draft:
            drafts["linkedin"] = li_draft.strip()

        # Humanizer pass
        if drafts:
            for platform, draft in drafts.items():
                human_prompt = (
                    f"You are the Humanizer. Review this {platform} post for AI writing patterns.\n\n"
                    f"Voice guide:\n{voice[:1000]}\n\n"
                    f"Post:\n{draft}\n\n"
                    f"Fix any AI-sounding patterns (em dashes, 'I run agents', corporate tone, "
                    f"filler words). Keep the substance. Output ONLY the revised post text."
                )
                revised, _ = run_claude_prompt(human_prompt, task_type="humanizer")
                if revised:
                    drafts[platform] = revised.strip()

        return drafts

    def _format_drafts(self, drafts: dict) -> str:
        """Format drafts for Slack display."""
        lines = ["Here are your drafts:\n"]
        for platform, draft in drafts.items():
            char_count = len(draft)
            lines.append(f"*{platform.title()}* ({char_count} chars):")
            lines.append(f"```{draft}```")
            lines.append("")

        lines.append("Reply: *ALL* to post both, *BLUESKY* or *LINKEDIN* for one, *SKIP* to cancel.")
        lines.append("Or reply with edited text to replace a draft.")
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

    def _load_social_config(self) -> dict:
        """Load social-config.json from project root."""
        config_path = PROJECT_ROOT / "social-config.json"
        with open(config_path) as f:
            return json.load(f)

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
                logger.error(f"Failed to post to {platform}: {e}")
                results[platform] = {"success": False, "error": str(e)}

        return results
