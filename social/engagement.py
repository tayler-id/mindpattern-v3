"""Engagement pipeline — find, draft, approve, post replies.

Discovers relevant conversations on X, Bluesky, and LinkedIn, drafts replies
using the brand voice, runs them through approval, and posts with jitter.
All engagement actions are tracked in memory for cooldown enforcement.
"""

import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import memory
from orchestrator.agents import run_claude_prompt
from policies.engine import PolicyEngine
from social.approval import ApprovalGateway
from social.posting import XClient, BlueskyClient, LinkedInClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


class EngagementPipeline:
    """Find conversations, draft replies, get approval, post engagements.

    Runs after the main social pipeline. Uses today's research findings
    as context to find relevant conversations worth engaging with.
    """

    def __init__(self, user_id: str, config: dict, db):
        """
        Args:
            user_id: User running the pipeline (e.g. "ramsay").
            config: social-config.json contents.
            db: sqlite3.Connection from memory.get_db().
        """
        self.user_id = user_id
        self.config = config
        self.db = db
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        self.policy = PolicyEngine.load_social()
        self.approval = ApprovalGateway(config)
        self.engagement_config = config.get("engagement", {})
        self._platform_clients = self._init_platform_clients()

    def _init_platform_clients(self) -> dict:
        """Initialize API clients for each enabled platform."""
        clients = {}
        platforms = self.config.get("platforms", {})

        if platforms.get("x", {}).get("enabled"):
            clients["x"] = XClient(platforms["x"])
        if platforms.get("bluesky", {}).get("enabled"):
            clients["bluesky"] = BlueskyClient(platforms["bluesky"])
        if platforms.get("linkedin", {}).get("enabled"):
            clients["linkedin"] = LinkedInClient(platforms["linkedin"])

        return clients

    def run(self, *, dry_run: bool = False) -> dict:
        """Execute the engagement pipeline.

        Steps:
            1. Find conversations matching today's research (Sonnet)
            2. Filter: skip already-engaged authors (memory.check_engagement)
            3. Draft replies with voice guide + editorial corrections (Sonnet)
            4. Rate limit check (PolicyEngine, enforced not advisory)
            5. Approval gate (ApprovalGateway)
            6. Post replies + auto-follow (parallel per platform, with jitter)
            7. Log engagements to memory

        Args:
            dry_run: If True, find and draft but do not post or request approval.

        Returns:
            {
                candidates_found, replies_drafted, replies_approved,
                replies_posted, follows, errors
            }
        """
        result = {
            "candidates_found": 0,
            "replies_drafted": 0,
            "replies_approved": 0,
            "replies_posted": 0,
            "follows": 0,
            "errors": [],
        }

        # ── Step 1: Find candidates ──────────────────────────────────
        logger.info("Engagement Step 1: Finding conversation candidates")
        try:
            candidates = self._find_candidates(self.date_str)
        except Exception as e:
            logger.error(f"Candidate search failed: {e}")
            result["errors"].append(f"Candidate search: {e}")
            return result

        result["candidates_found"] = len(candidates)
        logger.info(f"Found {len(candidates)} candidates across all platforms")

        if not candidates:
            logger.info("No engagement candidates found")
            return result

        # ── Step 2: Filter already-engaged authors ───────────────────
        logger.info("Engagement Step 2: Filtering already-engaged authors")
        filtered = []
        for c in candidates:
            author_id = c.get("author_id", "")
            platform = c.get("platform", "")

            if not author_id:
                filtered.append(c)
                continue

            engagement_check = memory.check_engagement(
                self.db, target_author_id=author_id, platform=platform
            )
            if engagement_check["already_engaged"]:
                logger.debug(
                    f"Skipping {c.get('author')} on {platform} "
                    f"(engaged {engagement_check['count']}x this week)"
                )
                continue

            filtered.append(c)

        skipped = len(candidates) - len(filtered)
        if skipped:
            logger.info(f"Filtered out {skipped} already-engaged authors")
        candidates = filtered

        if not candidates:
            logger.info("No candidates remaining after dedup filter")
            return result

        # ── Step 3: Draft replies ────────────────────────────────────
        logger.info(f"Engagement Step 3: Drafting replies for {len(candidates)} candidates")
        try:
            candidates = self._draft_replies(candidates)
        except Exception as e:
            logger.error(f"Reply drafting failed: {e}")
            result["errors"].append(f"Reply drafting: {e}")
            return result

        # Filter out candidates where drafting failed
        candidates = [c for c in candidates if c.get("our_reply")]
        result["replies_drafted"] = len(candidates)
        logger.info(f"Drafted {len(candidates)} replies")

        if not candidates:
            logger.info("No viable replies drafted")
            return result

        # ── Step 4: Rate limit check (enforced) ─────────────────────
        logger.info("Engagement Step 4: Rate limit enforcement")
        rate_limited = []
        for c in candidates:
            platform = c.get("platform", "")
            rate_check = self.policy.validate_rate_limits(
                self.db, platform, "reply"
            )
            if rate_check["allowed"]:
                rate_limited.append(c)
            else:
                logger.warning(
                    f"Rate limit blocks reply on {platform}: {rate_check['reason']}"
                )
                result["errors"].append(f"Rate limit ({platform}): {rate_check['reason']}")

        candidates = rate_limited

        # Also check global daily reply limit
        max_replies = self.engagement_config.get("max_replies_per_day", 30)
        if len(candidates) > max_replies:
            logger.info(
                f"Capping candidates from {len(candidates)} to {max_replies} "
                f"(daily limit)"
            )
            # Keep highest-relevance candidates
            candidates.sort(key=lambda c: c.get("relevance", 0), reverse=True)
            candidates = candidates[:max_replies]

        if not candidates:
            logger.info("No candidates remaining after rate limit check")
            return result

        if dry_run:
            logger.info(f"Dry run: would approve and post {len(candidates)} replies")
            result["replies_approved"] = len(candidates)
            return result

        # ── Step 5: Approval gate ────────────────────────────────────
        logger.info(f"Engagement Step 5: Requesting approval for {len(candidates)} replies")
        try:
            approval_response = self.approval.request_engagement_approval(candidates)
        except Exception as e:
            logger.error(f"Engagement approval failed: {e}")
            result["errors"].append(f"Approval: {e}")
            return result

        approved_indices = approval_response.get("approved_indices", [])
        result["replies_approved"] = len(approved_indices)

        if not approved_indices:
            logger.info(
                f"No replies approved: {approval_response.get('reason', 'unknown')}"
            )
            return result

        approved_candidates = [
            candidates[i] for i in approved_indices if i < len(candidates)
        ]
        logger.info(f"Approved {len(approved_candidates)} replies")

        # ── Step 6: Post replies + auto-follow (with jitter) ─────────
        logger.info("Engagement Step 6: Posting replies")
        posting_config = self.policy.rules.get("posting", {})
        jitter_range = posting_config.get("jitter_range_seconds", [60, 300])

        # Group by platform for efficient posting
        by_platform = {}
        for c in approved_candidates:
            platform = c.get("platform", "")
            by_platform.setdefault(platform, []).append(c)

        total_posted = 0
        total_follows = 0

        for platform, platform_candidates in by_platform.items():
            for i, candidate in enumerate(platform_candidates):
                try:
                    post_result = self._post_engagement(candidate)

                    if post_result.get("reply_posted"):
                        total_posted += 1

                    if post_result.get("follow_success"):
                        total_follows += 1

                    if post_result.get("error"):
                        result["errors"].append(
                            f"Post ({platform}): {post_result['error']}"
                        )

                except Exception as e:
                    logger.error(f"Failed to post engagement on {platform}: {e}")
                    result["errors"].append(f"Post ({platform}): {e}")

                # Jitter between posts (skip after last one in this platform batch)
                if i < len(platform_candidates) - 1:
                    delay = random.uniform(jitter_range[0], jitter_range[1])
                    logger.debug(f"Jitter delay: {delay:.0f}s")
                    time.sleep(delay)

        result["replies_posted"] = total_posted
        result["follows"] = total_follows

        # ── Step 7: Log engagements ──────────────────────────────────
        logger.info(
            f"Engagement pipeline complete: {total_posted} replies posted, "
            f"{total_follows} follows, {len(result['errors'])} errors"
        )

        return result

    def _find_candidates(self, date_str: str) -> list[dict]:
        """Use engagement-finder agent (Sonnet) to search for conversations.

        Combines LLM-driven search (for semantic matching against today's
        research) with direct platform API searches for broader coverage.

        Args:
            date_str: Today's date (YYYY-MM-DD).

        Returns:
            List of candidate dicts:
            [{platform, post_id, post_cid, author, author_id, content, relevance}]
        """
        # Get today's research context for relevance matching
        context = memory.get_context(self.db, date_str)
        recent_findings = memory.search_findings(
            self.db, f"research {date_str}", limit=10
        )

        # Build search topics from findings
        topics = []
        for f in recent_findings:
            if isinstance(f, dict):
                topics.append(f.get("title", ""))
            elif hasattr(f, "__getitem__"):
                topics.append(f["title"])

        topics = [t for t in topics if t][:8]

        if not topics:
            logger.warning("No research findings to base engagement search on")
            topics = ["AI agents", "LLM applications", "developer tools"]

        # Get engagement config limits
        queries_per_platform = self.engagement_config.get(
            "search_queries_per_platform", 8
        )
        candidates_per_platform = self.engagement_config.get(
            "candidates_per_platform", 10
        )
        min_likes = self.engagement_config.get("min_likes", 3)
        max_likes = self.engagement_config.get("max_likes", 5000)
        min_followers = self.engagement_config.get("min_follower_count", 50)

        # Build the prompt for the engagement-finder agent
        topics_list = "\n".join(f"- {t}" for t in topics)
        platforms_list = ", ".join(self._platform_clients.keys())

        prompt = f"""You are an engagement finder for MindPattern, a technical AI newsletter.

## Today's Research Topics
{topics_list}

## Task
Find 5-10 high-quality social media conversations on each platform ({platforms_list})
that are relevant to today's research topics. These should be conversations where
a thoughtful, knowledgeable reply would add value.

## Criteria
- Post must have between {min_likes} and {max_likes} likes/engagements
- Author must have at least {min_followers} followers
- Post should be from the last 48 hours
- Post should be substantive (not just a link drop or meme)
- Prefer posts asking questions or sharing opinions we can add to
- Avoid: political posts, drama threads, obvious promotional content

## Search Strategy
For each platform, search using variations of these topics. Try both direct
topic searches and broader related terms.

Search up to {queries_per_platform} queries per platform.
Return up to {candidates_per_platform} candidates per platform.

## Memory Context
{context[:2000] if context else "No prior context available."}

## Output Format
Output ONLY valid JSON:
{{
  "candidates": [
    {{
      "platform": "x|bluesky|linkedin",
      "post_id": "string",
      "post_cid": "string (bluesky only, empty otherwise)",
      "author": "display name",
      "author_id": "handle or ID",
      "content": "the post text",
      "relevance": 0.0-1.0,
      "reason": "why this is worth engaging with"
    }}
  ]
}}"""

        output, exit_code = run_claude_prompt(
            prompt=prompt,
            task_type="engagement_finder",
            allowed_tools=["Bash", "WebSearch", "WebFetch"],
        )

        candidates = []
        if exit_code == 0 and output:
            try:
                data = json.loads(output.strip())
                candidates = data.get("candidates", [])
            except json.JSONDecodeError:
                # Try to extract JSON from mixed output
                import re
                json_match = re.search(
                    r'\{[\s\S]*"candidates"[\s\S]*\}', output
                )
                if json_match:
                    try:
                        data = json.loads(json_match.group())
                        candidates = data.get("candidates", [])
                    except json.JSONDecodeError:
                        logger.warning("Could not parse engagement finder output")

        logger.info(f"Engagement finder returned {len(candidates)} candidates")
        return candidates

    def _draft_replies(self, candidates: list[dict]) -> list[dict]:
        """Use engagement-writer agent (Sonnet) to draft replies.

        Includes voice guide, editorial corrections, and platform character
        limits in the prompt. Drafts all replies in a single agent call for
        efficiency.

        Args:
            candidates: List of candidate dicts from _find_candidates().

        Returns:
            Same candidates with our_reply field added to each.
        """
        # Get voice calibration data
        corrections = memory.recent_corrections(self.db, limit=10)
        exemplars = memory.get_exemplars(self.db, limit=5)
        feedback_patterns = memory.get_feedback_patterns(self.db)

        # Build corrections context
        corrections_section = ""
        if corrections:
            examples = []
            for c in corrections:
                examples.append(
                    f"  BEFORE: {c['original_text'][:150]}\n"
                    f"  AFTER: {c['approved_text'][:150]}"
                )
            corrections_section = (
                "\n## Editorial Corrections (match this voice):\n"
                + "\n---\n".join(examples)
            )

        # Build exemplars context
        exemplars_section = ""
        if exemplars:
            ex_lines = []
            for e in exemplars:
                ex_lines.append(
                    f"  [{e['platform']}] {e['content'][:200]}"
                )
            exemplars_section = (
                "\n## Voice Exemplars (approved posts):\n"
                + "\n".join(ex_lines)
            )

        # Platform char limits
        platform_limits = {}
        for p_name, p_config in self.config.get("platforms", {}).items():
            platform_limits[p_name] = p_config.get(
                "max_chars", p_config.get("max_graphemes", 300)
            )

        # Format candidates for the prompt
        candidates_json = json.dumps(
            [
                {
                    "index": i,
                    "platform": c.get("platform"),
                    "author": c.get("author"),
                    "content": c.get("content", "")[:500],
                    "max_reply_chars": platform_limits.get(c.get("platform"), 280),
                }
                for i, c in enumerate(candidates)
            ],
            indent=2,
        )

        prompt = f"""You are an engagement reply writer for MindPattern, a technical AI newsletter.

## Voice Guide
- Casual, knowledgeable tone of a senior developer
- Add genuine value (insight, experience, data) — never generic "great point!"
- No hashtags, no emojis unless the conversation calls for it
- No em dashes. Use commas or periods instead.
- Keep replies concise — match the platform's vibe
- Never start with "Great point!" or "Interesting!" or similar filler
- When disagreeing, be respectful but direct
- Link to mindpattern.ai only if genuinely relevant, never forced
{corrections_section}
{exemplars_section}

## Candidates to Reply To
{candidates_json}

## Task
Draft a reply for EACH candidate. Each reply should:
1. Add substantive value to the conversation
2. Stay within the platform's character limit
3. Match our voice guide
4. Feel like a natural human reply, not a bot

## Output Format
Output ONLY valid JSON:
{{
  "replies": [
    {{
      "index": 0,
      "reply": "the reply text",
      "should_follow": true
    }}
  ]
}}

Set should_follow to true if the author seems worth following for ongoing
engagement (quality content in our space)."""

        output, exit_code = run_claude_prompt(
            prompt=prompt,
            task_type="engagement_writer",
        )

        if exit_code != 0 or not output:
            logger.error("Engagement writer failed")
            return candidates

        try:
            data = json.loads(output.strip())
            replies = data.get("replies", [])
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{[\s\S]*"replies"[\s\S]*\}', output)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    replies = data.get("replies", [])
                except json.JSONDecodeError:
                    logger.warning("Could not parse engagement writer output")
                    return candidates
            else:
                logger.warning("No JSON found in engagement writer output")
                return candidates

        # Merge replies back into candidates
        reply_map = {r["index"]: r for r in replies}
        for i, c in enumerate(candidates):
            if i in reply_map:
                c["our_reply"] = reply_map[i].get("reply", "")
                c["should_follow"] = reply_map[i].get("should_follow", False)

        return candidates

    def _post_engagement(self, candidate: dict) -> dict:
        """Post a single reply + auto-follow.

        Posts the reply via the platform client, optionally follows the author,
        and logs everything to memory.

        Args:
            candidate: Dict with platform, post_id, author_id, our_reply,
                       should_follow, etc.

        Returns:
            {reply_posted: bool, follow_success: bool, error: str | None}
        """
        platform = candidate.get("platform", "")
        post_id = candidate.get("post_id", "")
        post_cid = candidate.get("post_cid", "")
        author_id = candidate.get("author_id", "")
        our_reply = candidate.get("our_reply", "")
        should_follow = candidate.get("should_follow", False)

        client = self._platform_clients.get(platform)
        if not client:
            return {
                "reply_posted": False,
                "follow_success": False,
                "error": f"No client for {platform}",
            }

        result = {
            "reply_posted": False,
            "follow_success": False,
            "error": None,
        }

        # Post the reply
        try:
            reply_result = client.reply(
                post_id=post_id,
                text=our_reply,
                post_cid=post_cid,
            )
            result["reply_posted"] = True

            # Log the reply engagement
            memory.store_engagement(
                self.db,
                user_id=self.user_id,
                platform=platform,
                engagement_type="reply",
                target_post_url=candidate.get("target_post_url"),
                target_author=candidate.get("author"),
                target_author_id=author_id,
                target_content=candidate.get("content"),
                our_reply=our_reply,
                status="posted",
            )

            logger.info(
                f"Reply posted on {platform} to @{candidate.get('author', '?')}"
            )

        except Exception as e:
            result["error"] = f"Reply failed: {e}"
            logger.error(f"Reply failed on {platform}: {e}")

            # Log failed attempt
            memory.store_engagement(
                self.db,
                user_id=self.user_id,
                platform=platform,
                engagement_type="reply",
                target_author=candidate.get("author"),
                target_author_id=author_id,
                target_content=candidate.get("content"),
                our_reply=our_reply,
                status="failed",
            )
            return result

        # Auto-follow if suggested and within rate limits
        if should_follow and author_id:
            follow_check = self.policy.validate_rate_limits(
                self.db, platform, "follow"
            )
            if follow_check["allowed"]:
                try:
                    client.follow(author_id)
                    result["follow_success"] = True

                    memory.store_engagement(
                        self.db,
                        user_id=self.user_id,
                        platform=platform,
                        engagement_type="follow",
                        target_author=candidate.get("author"),
                        target_author_id=author_id,
                        status="posted",
                    )

                    logger.debug(f"Followed @{candidate.get('author')} on {platform}")

                except Exception as e:
                    logger.warning(
                        f"Follow failed for @{candidate.get('author')} "
                        f"on {platform}: {e}"
                    )
            else:
                logger.debug(
                    f"Follow rate limit hit for {platform}: "
                    f"{follow_check['reason']}"
                )

        return result
