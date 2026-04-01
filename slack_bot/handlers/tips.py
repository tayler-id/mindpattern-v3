"""#mp-tips handler: Paste a tip → post as "Tayler'd Tip!" to Bluesky + LinkedIn.

Drop a tip in #mp-tips and the bot will:
1. Adapt it for Bluesky (300 char limit) and LinkedIn (800-1350 chars)
2. Run humanizer to remove AI patterns
3. Post drafts back in a thread for approval
4. Post to both platforms on approval
"""

import json
import logging
import sys
from pathlib import Path

from slack_bot.handlers.base import BaseHandler

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TipsHandler(BaseHandler):
    """Handle messages in #mp-tips — tip to social post as Tayler'd Tip!"""

    def handle(self, event: dict) -> None:
        """Process a tip message."""
        text = event.get("text", "").strip()
        ts = event.get("ts", "")

        if not text or len(text) < 20:
            if text.lower() in ("help", "?"):
                self.reply(
                    "Paste a tip here. I'll format it as a *Tayler'd Tip!* post "
                    "for Bluesky and LinkedIn, then post it after you approve.",
                    thread_ts=ts,
                )
            return

        self.react("bulb", ts)
        self.reply("Formatting as Tayler'd Tip! for Bluesky + LinkedIn...", thread_ts=ts)

        try:
            drafts = self._create_drafts(text)
        except Exception as e:
            logger.error(f"[mp-tips] Pipeline failed: {e}", exc_info=True)
            self.reply(f"Failed: {e}", thread_ts=ts)
            return

        if not drafts:
            self.reply("Couldn't create drafts from that. Try a more specific tip.", thread_ts=ts)
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

        # Show drafts for approval
        lines = ["Here are your drafts:\n"]
        for platform, draft in drafts.items():
            lines.append(f"*{platform.title()}* ({len(draft)} chars):")
            lines.append(f"```{draft}```")
            lines.append("")
        lines.append("Reply *ALL* to post both, *BLUESKY* or *LINKEDIN* for one, *SKIP* to cancel.")
        lines.append("Or paste edited text to replace a draft.")
        self.reply("\n".join(lines), thread_ts=ts)

        # Wait for approval
        reply_text = self.wait_for_reply(ts)
        if not reply_text:
            self.reply("No response — cancelled.", thread_ts=ts)
            return

        reply_lower = reply_text.lower().strip()
        if reply_lower in ("skip", "no", "cancel", "n"):
            self.reply("Skipped.", thread_ts=ts)
            return

        # Determine which platforms
        platforms = list(drafts.keys())
        if reply_lower in ("all", "yes", "y", "go", "post"):
            approved = platforms
        else:
            approved = [p for p in platforms if p.lower() in reply_lower]
            if not approved:
                approved = platforms

        # Post
        self.reply(f"Posting to: {', '.join(approved)}...", thread_ts=ts)
        results = self._post(drafts, approved)

        result_lines = []
        for platform, result in results.items():
            if result.get("success"):
                result_lines.append(f":white_check_mark: {platform}: {result.get('url', 'posted')}")
            else:
                result_lines.append(f":x: {platform}: {result.get('error', 'unknown')}")
        self.reply("\n".join(result_lines), thread_ts=ts)

    def _load_identity(self) -> str:
        """Load voice.md for humanizer."""
        from memory.vault import read_source_file
        vault_dir = PROJECT_ROOT / "data" / "ramsay" / "mindpattern"
        return read_source_file(vault_dir / "voice.md")

    def _load_social_config(self) -> dict:
        """Load social-config.json."""
        with open(PROJECT_ROOT / "social-config.json") as f:
            return json.load(f)

    def _create_drafts(self, tip_text: str) -> dict:
        """Take a raw tip, create platform-specific drafts."""
        from orchestrator.agents import run_claude_prompt

        voice = self._load_identity()
        drafts = {}

        # Bluesky (300 chars max)
        bs_prompt = (
            f"## Voice Guide\n{voice}\n\n"
            f"## Task\nConvert this tip into a Bluesky post.\n\n"
            f"Tip:\n{tip_text}\n\n"
            f"HARD LIMIT: 300 characters total.\n"
            f"Start the post with \"Tayler'd Tip!\" on its own line.\n"
            f"Keep the actionable insight. Be specific. Lowercase fine.\n"
            f"Include https://mindpattern.ai at end if space allows.\n"
            f"Check EVERY banned word and banned self-reference in the voice guide.\n\n"
            f"Output ONLY the post text."
        )
        logger.info(f"[mp-tips] Bluesky writer: {len(bs_prompt)} chars")
        bs_draft, bs_exit = run_claude_prompt(bs_prompt, task_type="writer")
        logger.info(f"[mp-tips] Bluesky result: exit={bs_exit}, len={len(bs_draft) if bs_draft else 0}")
        if bs_draft and bs_draft.strip():
            drafts["bluesky"] = bs_draft.strip()
        else:
            logger.warning(f"[mp-tips] Bluesky writer empty (exit={bs_exit})")

        # LinkedIn (800-1350 chars)
        li_prompt = (
            f"## Voice Guide\n{voice}\n\n"
            f"## Task\nConvert this tip into a LinkedIn post.\n\n"
            f"Tip:\n{tip_text}\n\n"
            f"Target: 800-1350 characters.\n"
            f"Start the post with \"Tayler'd Tip!\" on its own line.\n"
            f"Expand on the tip with context and opinion. Why does this matter?\n"
            f"Be specific: name tools, versions, numbers.\n"
            f"No hashtags. No emoji bullets.\n"
            f"End with https://mindpattern.ai\n"
            f"Check EVERY banned word and banned self-reference in the voice guide.\n\n"
            f"Output ONLY the post text."
        )
        logger.info(f"[mp-tips] LinkedIn writer: {len(li_prompt)} chars")
        li_draft, li_exit = run_claude_prompt(li_prompt, task_type="writer")
        logger.info(f"[mp-tips] LinkedIn result: exit={li_exit}, len={len(li_draft) if li_draft else 0}")
        if li_draft and li_draft.strip():
            drafts["linkedin"] = li_draft.strip()
        else:
            logger.warning(f"[mp-tips] LinkedIn writer empty (exit={li_exit})")

        if not drafts:
            return drafts

        # Humanizer pass
        for platform, draft in list(drafts.items()):
            human_prompt = (
                f"## Voice Guide\n{voice}\n\n"
                f"## Task\nRemove AI writing patterns from this {platform} post.\n\n"
                f"Post:\n{draft}\n\n"
                f"Check for: em dashes, mirror sentences, anaphora, snappy triads, "
                f"banned words, hedge phrases, throat-clearing, neat-bow closings, "
                f"corporate tone, AND banned self-references (project names, resume, credentials).\n\n"
                f"IMPORTANT: Keep \"Tayler'd Tip!\" as the first line exactly as-is.\n\n"
                f"Read it aloud. Does it sound like a person or a press release?\n\n"
                f"Output ONLY the revised post text. No explanation. No notes about what you changed. "
                f"No '---' separator. No 'Changes made:' section. JUST the post text and nothing else."
            )
            revised, human_exit = run_claude_prompt(human_prompt, task_type="humanizer")
            logger.info(f"[mp-tips] Humanizer {platform}: exit={human_exit}, len={len(revised) if revised else 0}")
            if revised and revised.strip():
                drafts[platform] = revised.strip()

        return drafts

    def _post(self, drafts: dict, platforms: list[str]) -> dict:
        """Post to approved platforms."""
        from social.posting import BlueskyClient, LinkedInClient

        config = self._load_social_config()
        results = {}

        for platform in platforms:
            draft = drafts.get(platform)
            if not draft:
                continue
            try:
                if platform == "bluesky":
                    client = BlueskyClient(config["platforms"]["bluesky"])
                    result = client.post(draft)
                    results[platform] = {"success": True, "url": result.get("url", "")}
                elif platform == "linkedin":
                    client = LinkedInClient(config["platforms"]["linkedin"])
                    result = client.post(draft)
                    results[platform] = {"success": True, "url": result.get("url", "")}
            except Exception as e:
                logger.error(f"[mp-tips] Failed to post to {platform}: {e}")
                results[platform] = {"success": False, "error": str(e)}

        return results
