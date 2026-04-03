"""#mp-engagement handler: search for people, draft replies, reply sniper.

Two modes:
1. Search: type a topic → bot finds conversations on Bluesky/LinkedIn,
   drafts replies, shows candidates for approval
2. Reply sniper: paste a post URL → bot reads the post, drafts a reply
   in your voice, you approve → bot posts the reply
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


def _load_social_config() -> dict:
    """Load social-config.json from project root."""
    config_path = PROJECT_ROOT / "social-config.json"
    with open(config_path) as f:
        return json.load(f)


class EngagementHandler(BaseHandler):
    """Handle messages in #mp-engagement."""

    def handle(self, event: dict) -> None:
        text = event.get("text", "").strip()
        ts = event.get("ts", "")

        # Check if it's a URL (reply sniper mode)
        urls = self.extract_urls(text)
        if urls:
            self._handle_reply_sniper(urls[0], ts)
            return

        # Otherwise treat as a search query
        if text.lower() in ("help", "?"):
            self.reply(
                "Two ways to use this channel:\n"
                "1. *Search:* Type a topic (e.g. 'MCP servers') and I'll find people talking about it\n"
                "2. *Reply sniper:* Paste a post URL and I'll draft a reply in your voice",
                thread_ts=ts,
            )
            return

        if len(text) < 3:
            return  # Too short to be a meaningful query

        self._handle_search(text, ts)

    def _handle_reply_sniper(self, url: str, ts: str) -> None:
        """Read a post URL, draft a reply, wait for approval, post it."""
        self.react("eyes", ts)
        self.reply("Reading that post...", thread_ts=ts)

        content = self.read_url(url)
        if not content:
            self.reply("Couldn't read that post. It might be private or the URL is wrong.", thread_ts=ts)
            return

        post_text = content[:3000]

        # Draft a reply
        self.reply("Drafting a reply in your voice...", thread_ts=ts)

        try:
            from orchestrator.agents import run_claude_prompt
            from memory.vault import read_source_file

            vault_dir = PROJECT_ROOT / "data" / "ramsay" / "mindpattern"
            voice = read_source_file(vault_dir / "voice.md")
            soul = read_source_file(vault_dir / "soul.md")

            prompt = (
                f"You are drafting a reply to this social media post.\n\n"
                f"Post URL: {url}\n"
                f"Post content:\n{post_text}\n\n"
                f"Your identity:\n{soul[:500]}\n\n"
                f"Voice guide:\n{voice[:1000]}\n\n"
                f"Write a thoughtful, genuine reply. Be specific to what they said. "
                f"Add value — share a relevant insight, ask a smart question, or build on their point. "
                f"Keep it concise (1-3 sentences). No AI patterns (em dashes, 'fascinating', 'great point'). "
                f"Output ONLY the reply text."
            )
            reply_draft, _ = run_claude_prompt(prompt, task_type="engagement")

        except Exception as e:
            logger.error(f"Failed to draft reply: {e}")
            self.reply(f"Failed to draft reply: {e}", thread_ts=ts)
            return

        if not reply_draft:
            self.reply("Couldn't generate a reply. Try a different post.", thread_ts=ts)
            return

        # Show the draft
        self.reply(
            f"Here's my draft reply:\n```{reply_draft.strip()}```\n\n"
            f"Reply *GO* to post it, *SKIP* to cancel, or paste your own version.",
            thread_ts=ts,
        )

        # Wait for approval
        approval = self.wait_for_reply(ts)
        if not approval or approval.lower() in ("skip", "no", "cancel"):
            self.reply("Skipped.", thread_ts=ts)
            return

        # If user pasted their own text (not just "go"), use that instead
        final_reply = reply_draft.strip()
        if approval.lower() not in ("go", "yes", "y", "post"):
            final_reply = approval  # User provided their own text

        # Detect platform from URL and post
        self._post_reply(url, final_reply, ts)

    def _handle_search(self, query: str, ts: str) -> None:
        """Search for real conversations matching a query and show candidates.

        Uses BlueskyClient.search() (AT Protocol API) to find REAL posts.
        Engagement is Bluesky-only. Never generates placeholder or
        hallucinated candidates.
        """
        self.react("mag", ts)
        self.reply(f"Searching for conversations about: *{query}*...", thread_ts=ts)

        try:
            config = _load_social_config()
            results = []

            # Search Bluesky via AT Protocol API
            bsky_config = config.get("platforms", {}).get("bluesky", {})
            if bsky_config.get("enabled"):
                try:
                    from social.posting import BlueskyClient
                    client = BlueskyClient(bsky_config)
                    bsky_results = client.search(query, max_results=10)
                    for post in bsky_results:
                        post["_source"] = "bluesky_api"
                    results.extend(bsky_results)
                except Exception as e:
                    logger.warning(f"Bluesky search failed: {e}")

            # LinkedIn engagement removed — no reliable search API.
            # Engagement is Bluesky-only.

            # Validate: reject any results without real URLs or handles
            validated = []
            for post in results:
                url = post.get("url", "")
                handle = post.get("author_handle", post.get("author", ""))
                text = post.get("text", "")

                # Reject placeholder/hallucinated data
                if not url or not handle:
                    continue
                if "johndoe" in handle.lower() or "example" in url.lower():
                    logger.warning(f"Rejected placeholder candidate: @{handle} {url}")
                    continue
                if len(text.strip()) < 10:
                    continue

                validated.append(post)

            results = validated

            if not results:
                self.reply("No engagement candidates found. Try a different query.", thread_ts=ts)
                return

            # Format results -- use flat field names from BlueskyClient.search()
            lines = [f"Found {len(results)} posts about *{query}*:\n"]
            for i, post in enumerate(results[:5], 1):
                platform = post.get("platform", "bluesky")
                author = post.get("author_handle", post.get("author", "unknown"))
                text = post.get("text", "")[:150]
                url = post.get("url", "")
                lines.append(f"*{i}.* [{platform}] @{author}")
                lines.append(f"   {text}")
                if url:
                    lines.append(f"   {url}")
                lines.append("")

            lines.append("Reply with a number (1-5) to draft a reply, or *SKIP* to cancel.")
            self.reply("\n".join(lines), thread_ts=ts)

            # Wait for selection
            selection = self.wait_for_reply(ts)
            if not selection or selection.lower() in ("skip", "cancel"):
                self.reply("Skipped.", thread_ts=ts)
                return

            # Parse selection
            try:
                idx = int(selection.strip()) - 1
                if 0 <= idx < len(results):
                    selected = results[idx]
                    post_uri = selected.get("uri", selected.get("url", ""))
                    post_text = selected.get("text", "")
                    author = selected.get("author_handle", selected.get("author", "unknown"))

                    self.reply(f"Drafting reply to @{author}...", thread_ts=ts)
                    self._draft_and_approve_reply(post_text, author, post_uri, ts)
                else:
                    self.reply("Invalid selection.", thread_ts=ts)
            except ValueError:
                self.reply("Please reply with a number (1-5).", thread_ts=ts)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            self.reply(f"Search failed: {e}", thread_ts=ts)

    def _draft_and_approve_reply(self, post_text: str, author: str, post_uri: str, ts: str):
        """Draft a reply, show for approval, post if approved."""
        from orchestrator.agents import run_claude_prompt
        from memory.vault import read_source_file

        vault_dir = PROJECT_ROOT / "data" / "ramsay" / "mindpattern"
        voice = read_source_file(vault_dir / "voice.md")

        prompt = (
            f"Draft a reply to this post by @{author}:\n\n"
            f"{post_text}\n\n"
            f"Voice guide:\n{voice[:1000]}\n\n"
            f"Write a thoughtful, genuine reply (1-3 sentences). "
            f"Output ONLY the reply text."
        )
        draft, _ = run_claude_prompt(prompt, task_type="engagement")

        if not draft:
            self.reply("Couldn't generate a reply.", thread_ts=ts)
            return

        self.reply(
            f"Reply to @{author}:\n```{draft.strip()}```\n\n"
            f"*GO* to post, *SKIP* to cancel, or paste your own version.",
            thread_ts=ts,
        )

        approval = self.wait_for_reply(ts)
        if not approval or approval.lower() in ("skip", "no", "cancel"):
            self.reply("Skipped.", thread_ts=ts)
            return

        final = draft.strip()
        if approval.lower() not in ("go", "yes", "y"):
            final = approval

        # Post the reply
        try:
            config = _load_social_config()
            bsky_config = config.get("platforms", {}).get("bluesky", {})
            if not bsky_config.get("enabled"):
                self.reply(
                    f"Bluesky is not enabled. Here's your reply to post manually:\n"
                    f"```{final}```",
                    thread_ts=ts,
                )
                return
            from social.posting import BlueskyClient
            client = BlueskyClient(bsky_config)
            client.reply(final, post_uri)
            self.reply(f"Replied to @{author}", thread_ts=ts)
        except Exception as e:
            self.reply(f"Failed to post reply: {e}", thread_ts=ts)

    def _post_reply(self, url: str, reply_text: str, ts: str) -> None:
        """Post a reply to the correct platform based on URL."""
        if "bsky.app" in url or "bsky.social" in url:
            try:
                config = _load_social_config()
                bsky_config = config.get("platforms", {}).get("bluesky", {})
                if not bsky_config.get("enabled"):
                    self.reply(
                        f"Bluesky is not enabled. Here's your reply to post manually:\n"
                        f"```{reply_text}```",
                        thread_ts=ts,
                    )
                    return
                from social.posting import BlueskyClient
                client = BlueskyClient(bsky_config)
                client.reply(reply_text, url)
                self.reply("Reply posted to Bluesky", thread_ts=ts)
            except Exception as e:
                self.reply(f"Failed to post reply: {e}", thread_ts=ts)
        elif "linkedin.com" in url:
            # LinkedIn replies need manual posting
            self.reply(
                f"LinkedIn replies need manual posting. Here's your reply to copy:\n"
                f"```{reply_text}```\n"
                f"Post URL: {url}",
                thread_ts=ts,
            )
        else:
            self.reply(
                f"I can only auto-post replies to Bluesky. Here's your reply:\n"
                f"```{reply_text}```",
                thread_ts=ts,
            )
