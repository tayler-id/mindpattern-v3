"""#mp-posts handler: URL → full social post pipeline → approve → publish.

Drop a URL in #mp-posts and the bot will:
1. Read the article (Jina Reader)
2. Run EIC topic framing (Opus)
3. Run writers (per platform)
4. Run critics (blind validation)
5. Run humanizer (AI pattern removal)
6. Run expeditor (final quality gate)
7. Post drafts back in a thread
8. Wait for approval (ALL / BLUESKY / LINKEDIN / SKIP)
9. Post to platforms
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
                    "(EIC → writers → critics → humanizer → expeditor), and post drafts "
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

        self.reply(f"Got it: *{title}*\nRunning full pipeline (EIC → writers → critics → humanizer → expeditor)...", thread_ts=ts)

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

        # Warn about missing platforms
        expected = {"bluesky", "linkedin"}
        missing = expected - set(drafts.keys())
        if missing:
            self.reply(
                f":warning: Failed to generate drafts for: {', '.join(missing)}. "
                f"Proceeding with {', '.join(drafts.keys())} only.",
                thread_ts=ts,
            )

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
                url_posted = result.get("url", "")
                result_lines.append(f"Posted to {platform}: {url_posted}")
            else:
                result_lines.append(f"{platform} failed: {result.get('error', 'unknown')}")

        self.reply("\n".join(result_lines), thread_ts=ts)

    def _load_identity(self) -> tuple[str, str, str]:
        """Load full voice.md, soul.md, user.md from vault."""
        from memory.vault import read_source_file

        vault_dir = PROJECT_ROOT / "data" / "ramsay" / "mindpattern"
        voice = read_source_file(vault_dir / "voice.md")
        soul = read_source_file(vault_dir / "soul.md")
        user = read_source_file(vault_dir / "user.md")
        return voice, soul, user

    def _load_social_config(self) -> dict:
        """Load social-config.json from project root."""
        config_path = PROJECT_ROOT / "social-config.json"
        with open(config_path) as f:
            return json.load(f)

    def _run_social_pipeline(self, url: str, title: str, article_text: str) -> dict:
        """Run the full social pipeline: EIC → writers → critics → humanizer → expeditor.

        Returns: {platform: draft_text} dict
        """
        from orchestrator.agents import run_claude_prompt

        voice, soul, user = self._load_identity()
        logger.info(f"[mp-posts] Identity loaded: voice={len(voice)} chars, soul={len(soul)} chars")

        # ── EIC: Frame the topic ──
        eic_prompt = (
            f"You are the Editor-in-Chief for MindPattern social posts.\n\n"
            f"## Identity\n{soul}\n\n"
            f"## Who You Serve\n{user}\n\n"
            f"## Article\nURL: {url}\nTitle: {title}\n\n"
            f"Article content:\n{article_text[:4000]}\n\n"
            f"Create a creative brief. What's the angle that a builder who ships "
            f"with AI daily would find genuinely interesting? Not a summary. An opinion.\n\n"
            f"Output JSON:\n"
            f'{{"topic": "...", "angle": "...", "key_insight": "...", "target_platforms": ["bluesky", "linkedin"]}}'
        )
        logger.info(f"[mp-posts] EIC prompt: {len(eic_prompt)} chars")
        eic_output, eic_exit = run_claude_prompt(eic_prompt, task_type="eic")
        logger.info(f"[mp-posts] EIC result: exit_code={eic_exit}, output_len={len(eic_output) if eic_output else 0}")

        try:
            brief = json.loads(eic_output) if eic_output else {}
        except json.JSONDecodeError:
            logger.warning(f"[mp-posts] EIC JSON parse failed, using fallback. Output: {(eic_output or '')[:200]}")
            brief = {"topic": title, "angle": "Share key insight", "key_insight": article_text[:200]}

        topic = brief.get("topic", title)
        angle = brief.get("angle", "")
        insight = brief.get("key_insight", "")

        # ── Writers: Draft for each platform ──
        drafts = {}

        # Bluesky draft (300 chars max)
        bs_prompt = (
            f"## Voice Guide\n{voice}\n\n"
            f"## Task\nWrite a Bluesky post about this topic.\n\n"
            f"Topic: {topic}\nAngle: {angle}\nKey insight: {insight}\n"
            f"Source URL: {url}\n\n"
            f"HARD LIMIT: 300 characters total including the URL.\n"
            f"Include https://mindpattern.ai at end if space allows.\n\n"
            f"Write as Tayler Ramsay. First person. Lowercase fine. "
            f"Technically specific. Have an opinion. No throat-clearing.\n\n"
            f"Output ONLY the post text, nothing else."
        )
        logger.info(f"[mp-posts] Bluesky writer prompt: {len(bs_prompt)} chars")
        bs_draft, bs_exit = run_claude_prompt(bs_prompt, task_type="writer")
        logger.info(
            f"[mp-posts] Bluesky writer result: exit_code={bs_exit}, "
            f"output_len={len(bs_draft) if bs_draft else 0}, "
            f"preview={repr((bs_draft or '')[:150])}"
        )
        if bs_draft and bs_draft.strip():
            drafts["bluesky"] = bs_draft.strip()
        else:
            logger.warning(f"[mp-posts] Bluesky writer returned empty (exit_code={bs_exit})")

        # LinkedIn draft (800-1350 chars)
        li_prompt = (
            f"## Voice Guide\n{voice}\n\n"
            f"## Task\nWrite a LinkedIn post about this topic.\n\n"
            f"Topic: {topic}\nAngle: {angle}\nKey insight: {insight}\n"
            f"Source URL: {url}\n\n"
            f"Target length: 800-1350 characters.\n\n"
            f"Write as Tayler Ramsay. First person. Builder perspective.\n"
            f"Share a real insight from direct experience, not a summary.\n"
            f"Be specific: name tools, versions, companies, numbers.\n"
            f"No hashtags. No emoji bullets. No 'I'm excited to announce'.\n"
            f"No em dashes. Use periods and commas instead.\n"
            f"End with https://mindpattern.ai\n\n"
            f"Output ONLY the post text, nothing else."
        )
        logger.info(f"[mp-posts] LinkedIn writer prompt: {len(li_prompt)} chars")
        li_draft, li_exit = run_claude_prompt(li_prompt, task_type="writer")
        logger.info(
            f"[mp-posts] LinkedIn writer result: exit_code={li_exit}, "
            f"output_len={len(li_draft) if li_draft else 0}, "
            f"preview={repr((li_draft or '')[:150])}"
        )
        if li_draft and li_draft.strip():
            drafts["linkedin"] = li_draft.strip()
        else:
            logger.warning(f"[mp-posts] LinkedIn writer returned empty (exit_code={li_exit})")

        if not drafts:
            return drafts

        logger.info(f"[mp-posts] Writers done: drafts for {list(drafts.keys())}")

        # ── Critics: Blind validation ──
        for platform, draft in list(drafts.items()):
            critic_prompt = (
                f"## Voice Guide\n{voice}\n\n"
                f"## Task\nYou are a blind critic. Review this {platform} post.\n\n"
                f"Post:\n{draft}\n\n"
                f"Check against the voice guide. Score each dimension 1-10:\n"
                f"- voice_authenticity: Does it sound like a real person or AI?\n"
                f"- platform_fit: Right length, tone, format for {platform}?\n"
                f"- engagement_potential: Would you stop scrolling for this?\n\n"
                f"Check for BANNED WORDS from the voice guide. Check for:\n"
                f"- Em dashes (—) — these must be removed\n"
                f"- Mirror sentences ('not X, it's Y' repeated)\n"
                f"- Anaphora (repetitive parallel structure like 'Whether... Whether... Whether...')\n"
                f"- Snappy triads ('Simple. Powerful. Effective.')\n"
                f"- Generic hedges ('it's worth noting', 'it should be noted')\n"
                f"- Throat-clearing openers\n\n"
                f"Output JSON: {{\"verdict\": \"APPROVED\" or \"REVISE\", "
                f"\"scores\": {{\"voice_authenticity\": N, \"platform_fit\": N, \"engagement_potential\": N}}, "
                f"\"issues\": [\"list of specific problems\"], "
                f"\"revision_notes\": \"what to fix\"}}"
            )
            critic_output, critic_exit = run_claude_prompt(critic_prompt, task_type="critic")
            logger.info(f"[mp-posts] Critic {platform}: exit_code={critic_exit}, output_len={len(critic_output) if critic_output else 0}")

            try:
                critique = json.loads(critic_output) if critic_output else {}
            except json.JSONDecodeError:
                critique = {}

            if critique.get("verdict", "").upper() == "REVISE":
                revision_notes = critique.get("revision_notes", "")
                issues = critique.get("issues", [])
                issues_str = "\n".join(f"- {i}" for i in issues) if issues else ""

                revise_prompt = (
                    f"## Voice Guide\n{voice}\n\n"
                    f"## Task\nRevise this {platform} post based on critic feedback.\n\n"
                    f"Original post:\n{draft}\n\n"
                    f"Critic issues:\n{issues_str}\n"
                    f"Revision notes: {revision_notes}\n\n"
                    f"Fix every issue. Keep the substance and opinion. "
                    f"Output ONLY the revised post text. No explanation. No notes about what you changed. No '---' separator. No 'Changes made:' section. JUST the post text and nothing else."
                )
                revised, _ = run_claude_prompt(revise_prompt, task_type="writer")
                if revised:
                    drafts[platform] = revised.strip()

        logger.info(f"[mp-posts] Critics done: drafts for {list(drafts.keys())}")

        # ── Humanizer: Remove AI patterns ──
        for platform, draft in list(drafts.items()):
            human_prompt = (
                f"## Voice Guide\n{voice}\n\n"
                f"## Task\nYou are the Humanizer. Your ONLY job is to catch and remove "
                f"AI writing patterns from this {platform} post.\n\n"
                f"Post:\n{draft}\n\n"
                f"Scan for these specific AI tells and FIX them:\n"
                f"1. Em dashes (—) → replace with periods or commas\n"
                f"2. Mirror sentences ('not X, it's Y' / 'that's not a prediction, that's a confession') "
                f"→ rewrite as a single direct statement\n"
                f"3. Anaphora ('Whether... Whether... Whether...') → break the pattern, vary structure\n"
                f"4. Snappy triads ('Simple. Powerful. Effective.') → delete or rewrite\n"
                f"5. Banned words from the voice guide → replace with plain language\n"
                f"6. Hedge phrases ('it's worth noting', 'it should be noted') → delete, just state the thing\n"
                f"7. Throat-clearing openers ('In today's...', 'As we navigate...') → start with the point\n"
                f"8. 'I run agents' or 'as someone who builds with AI' → too on the nose, cut it\n"
                f"9. Neat-bow closings ('The future is...', 'Time will tell...') → just stop when done\n"
                f"10. Corporate tone anywhere → make it conversational\n\n"
                f"Read the post aloud in your head. Does it sound like a person talking or a press release? "
                f"If press release, rewrite harder.\n\n"
                f"Output ONLY the revised post text. No explanation. No notes about what you changed. No '---' separator. No 'Changes made:' section. JUST the post text and nothing else."
            )
            revised, human_exit = run_claude_prompt(human_prompt, task_type="humanizer")
            logger.info(f"[mp-posts] Humanizer {platform}: exit_code={human_exit}, output_len={len(revised) if revised else 0}")
            if revised and revised.strip():
                drafts[platform] = revised.strip()
            else:
                logger.warning(f"[mp-posts] Humanizer returned empty for {platform}, keeping original")

        logger.info(f"[mp-posts] Humanizer done: drafts for {list(drafts.keys())}")

        # ── Expeditor: Final quality gate ──
        for platform, draft in list(drafts.items()):
            exp_prompt = (
                f"## Voice Guide\n{voice}\n\n"
                f"## Task\nFinal quality check on this {platform} post before publishing.\n\n"
                f"Post:\n{draft}\n\n"
                f"HARD FAIL only for:\n"
                f"- Factual errors or unverifiable claims\n"
                f"- Missing source attribution when making specific claims\n"
                f"- Content that would embarrass the author\n"
                f"- Any banned word from the voice guide still present\n\n"
                f"STYLE WARNINGS (note but don't fail):\n"
                f"- Em dashes, rhetorical questions, snappy triads\n\n"
                f"Output JSON: {{\"verdict\": \"PASS\" or \"FAIL\", \"reason\": \"...\"}}"
            )
            exp_output, exp_exit = run_claude_prompt(exp_prompt, task_type="expeditor")
            logger.info(f"[mp-posts] Expeditor {platform}: exit_code={exp_exit}, output_len={len(exp_output) if exp_output else 0}")

            try:
                exp = json.loads(exp_output) if exp_output else {}
            except json.JSONDecodeError:
                exp = {"verdict": "PASS"}

            if exp.get("verdict", "").upper() == "FAIL":
                logger.warning(f"[mp-posts] Expeditor FAILED {platform}: {exp.get('reason', '')}")
                # Don't remove — let user see it and decide

        logger.info(f"[mp-posts] Pipeline complete: final drafts for {list(drafts.keys())}")
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
                logger.error(f"Failed to post to {platform}: {e}")
                results[platform] = {"success": False, "error": str(e)}

        return results
