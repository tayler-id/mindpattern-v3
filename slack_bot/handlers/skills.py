"""#mp-skills handler: Paste a skill tip → post to Bluesky + LinkedIn.

Drop a skill tip in #mp-skills and the bot will:
1. Adapt it for Bluesky (300 char limit) and LinkedIn (800-1350 chars)
2. Run humanizer to remove AI patterns
3. Post drafts back in a thread for approval
4. Post to both platforms on approval
"""

import json
import logging
import sys
from pathlib import Path

from slack_bot.approval import parse_platform_approval
from slack_bot.drafts import apply_draft_edit, parse_draft_edit
from slack_bot.handlers.base import BaseHandler

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SKILL_HEADER = "Skill of the Day!"


class SkillsHandler(BaseHandler):
    """Handle messages in #mp-skills — skill tip to social post."""

    def handle(self, event: dict) -> None:
        """Process a skill tip message."""
        text = event.get("text", "").strip()
        ts = event.get("ts", "")

        if not text or len(text) < 20:
            self.reply(
                "Paste a concrete skill tip here and I'll format it for Bluesky "
                "and LinkedIn, then post it after you approve.\n\n"
                "Example: `When an agent keeps looping, stop the run and ask it "
                "to identify the smallest failing assumption before trying "
                "another fix.`",
                thread_ts=ts,
            )
            return

        self.react("brain", ts)
        self.reply("Formatting for Bluesky + LinkedIn...", thread_ts=ts)

        try:
            drafts = self._create_drafts(text)
        except Exception as e:
            logger.error(f"Skills pipeline failed: {e}", exc_info=True)
            self.reply(f"Failed: {e}", thread_ts=ts)
            return

        if not drafts:
            self.reply("Couldn't create drafts from that. Try a more specific skill tip.", thread_ts=ts)
            return

        platforms = list(drafts.keys())
        self.reply(self._format_drafts(drafts), thread_ts=ts)

        # Wait for approval. Edit replies revise drafts and require a new
        # explicit approval reply before any posting can happen.
        while True:
            reply_text = self.wait_for_reply(ts)
            if not reply_text:
                self.reply("No response — cancelled.", thread_ts=ts)
                return

            edit, edit_error = parse_draft_edit(reply_text, platforms)
            if edit_error:
                self.reply(edit_error, thread_ts=ts)
                continue

            if edit:
                try:
                    drafts = apply_draft_edit(drafts, edit)
                except KeyError as e:
                    self.reply(str(e), thread_ts=ts)
                    continue
                self.reply(
                    f"Updated {edit.platform} draft.\n\n{self._format_drafts(drafts)}",
                    thread_ts=ts,
                )
                continue

            approved = parse_platform_approval(reply_text, platforms)
            if not approved:
                self.reply("Skipped. Nothing posted.", thread_ts=ts)
                return
            break

        # Post
        self.reply(f"Posting to: {', '.join(approved)}...", thread_ts=ts)
        results = self._post(drafts, approved)

        result_lines = []
        for platform, result in results.items():
            if result.get("success"):
                result_lines.append(f"Posted to {platform}: {result.get('url', '')}")
            elif result.get("manual_only"):
                result_lines.append(f"{platform} manual copy: {result.get('error', '')}")
                result_lines.append(f"```{result.get('content', '')}```")
            else:
                result_lines.append(f"{platform} failed: {result.get('error', 'unknown')}")
        self.reply("\n".join(result_lines), thread_ts=ts)

    def _format_drafts(self, drafts: dict[str, str]) -> str:
        """Format Slack draft previews."""
        lines = ["Here are your drafts:\n"]
        for platform, draft in drafts.items():
            lines.append(f"*{platform.title()}* ({len(draft)} chars):")
            lines.append(f"```{draft}```")
            lines.append("")
        lines.append("Reply *ALL* to post both, *BLUESKY* or *LINKEDIN* for one, *SKIP* to cancel.")
        lines.append("Or reply `edit bluesky: ...` or `edit linkedin: ...` to replace a draft.")
        return "\n".join(lines)

    def _load_identity(self) -> str:
        """Load voice.md for humanizer."""
        from memory.vault import read_source_file
        vault_dir = PROJECT_ROOT / "data" / "ramsay" / "mindpattern"
        return read_source_file(vault_dir / "voice.md")

    def _load_social_config(self) -> dict:
        """Load social-config.json."""
        with open(PROJECT_ROOT / "social-config.json") as f:
            return json.load(f)

    def _create_drafts(self, skill_text: str) -> dict:
        """Take a raw skill tip, create platform-specific drafts."""
        from orchestrator.agents import run_claude_prompt

        voice = self._load_identity()
        drafts = {}

        # Bluesky (300 chars max)
        bs_prompt = (
            f"## Voice Guide\n{voice}\n\n"
            f"## Task\nConvert this skill tip into a Bluesky post.\n\n"
            f"Skill tip:\n{skill_text}\n\n"
            f"HARD LIMIT: 300 characters total.\n"
            f"Start the post with 'Skill of the Day!' on its own line.\n"
            f"Keep the actionable insight. Be specific. Lowercase fine.\n"
            f"Include https://mindpattern.ai at end if space allows.\n"
            f"Check EVERY banned word and banned self-reference in the voice guide.\n\n"
            f"Output ONLY the post text."
        )
        bs_draft, _ = run_claude_prompt(bs_prompt, task_type="writer")
        if bs_draft:
            drafts["bluesky"] = bs_draft.strip()

        # LinkedIn (800-1350 chars)
        li_prompt = (
            f"## Voice Guide\n{voice}\n\n"
            f"## Task\nConvert this skill tip into a LinkedIn post.\n\n"
            f"Skill tip:\n{skill_text}\n\n"
            f"Target: 800-1350 characters.\n"
            f"Start the post with 'Skill of the Day!' on its own line.\n"
            f"Expand on the tip with context and opinion. Why does this matter?\n"
            f"Be specific: name tools, versions, numbers.\n"
            f"No hashtags. No emoji bullets.\n"
            f"End with https://mindpattern.ai\n"
            f"Check EVERY banned word and banned self-reference in the voice guide.\n\n"
            f"Output ONLY the post text."
        )
        li_draft, _ = run_claude_prompt(li_prompt, task_type="writer")
        if li_draft:
            drafts["linkedin"] = li_draft.strip()

        # Humanizer pass
        for platform, draft in list(drafts.items()):
            human_prompt = (
                f"## Voice Guide\n{voice}\n\n"
                f"## Task\nRemove AI writing patterns from this {platform} post.\n\n"
                f"Post:\n{draft}\n\n"
                f"Check for: em dashes, mirror sentences, anaphora, snappy triads, "
                f"banned words, hedge phrases, throat-clearing, neat-bow closings, "
                f"corporate tone, AND banned self-references (project names, resume, credentials).\n\n"
                f"Read it aloud. Does it sound like a person or a press release?\n\n"
                f"Output ONLY the revised post text. No explanation. No notes about what you changed. "
                f"No '---' separator. No 'Changes made:' section. JUST the post text and nothing else."
            )
            revised, _ = run_claude_prompt(human_prompt, task_type="humanizer")
            if revised:
                drafts[platform] = revised.strip()

        # The humanizer strips "Skill of the Day!" as a branded label — force it
        # back deterministically so the post always ships with the header.
        for platform, draft in list(drafts.items()):
            if not draft.lstrip().lower().startswith(SKILL_HEADER.lower()):
                drafts[platform] = f"{SKILL_HEADER}\n\n{draft.lstrip()}"

        return drafts

    def _post(self, drafts: dict, platforms: list[str]) -> dict:
        """Post to approved platforms."""
        from social.posting import BlueskyClient, LinkedInClient, manual_copy_result

        config = self._load_social_config()
        results = {}

        for platform in platforms:
            draft = drafts.get(platform)
            if not draft:
                continue
            platform_cfg = config.get("platforms", {}).get(platform, {})
            if not platform_cfg.get("enabled"):
                results[platform] = manual_copy_result(
                    platform,
                    draft,
                    f"{platform} is disabled; use manual copy.",
                )
                continue
            try:
                if platform == "bluesky":
                    client = BlueskyClient(platform_cfg)
                    result = client.post(draft)
                elif platform == "linkedin":
                    client = LinkedInClient(platform_cfg)
                    result = client.post(draft)
                else:
                    results[platform] = {"success": False, "error": f"Unknown platform: {platform}"}
                    continue

                if result.get("success"):
                    results[platform] = {"success": True, "url": result.get("url", "")}
                else:
                    results[platform] = {
                        "success": False,
                        "error": result.get("error", "unknown error"),
                    }
            except Exception as e:
                logger.error(f"Failed to post to {platform}: {e}")
                results[platform] = {"success": False, "error": str(e)}

        return results
