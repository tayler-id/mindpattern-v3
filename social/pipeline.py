"""Main social pipeline — replaces run-social.sh (1,259 lines of bash).

Orchestrates the full content creation flow: topic selection, brief creation,
art generation, multi-platform writing, critic review, policy validation,
humanization, expediting, approval, and posting with jitter.

All coordination is Python; LLM calls go through orchestrator.agents.run_claude_prompt.
"""

import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import memory
from orchestrator.agents import run_claude_prompt
from policies.engine import PolicyEngine
from social.approval import ApprovalGateway
from social.art import create_art
from social.eic import select_topic, create_brief
from social.writers import write_drafts, _humanize
from social.critics import review_draft, deterministic_validate, expedite
from social.posting import BlueskyClient, LinkedInClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


class SocialPipeline:
    """Full social content pipeline — topic to post.

    Replaces the monolithic run-social.sh with structured Python orchestration.
    Each step returns a dict; failures at any step produce a partial result
    with error context rather than crashing the whole pipeline.
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
        self._platform_clients = self._init_platform_clients()

    def _init_platform_clients(self) -> dict:
        """Initialize API clients for each enabled platform."""
        clients = {}
        platforms = self.config.get("platforms", {})

        if platforms.get("bluesky", {}).get("enabled"):
            clients["bluesky"] = BlueskyClient(platforms["bluesky"])
        if platforms.get("linkedin", {}).get("enabled"):
            clients["linkedin"] = LinkedInClient(platforms["linkedin"])

        return clients

    def _enabled_platforms(self, filter_list: list[str] | None = None) -> list[str]:
        """Get list of enabled platform names, optionally filtered."""
        enabled = list(self._platform_clients.keys())
        if filter_list:
            enabled = [p for p in enabled if p in filter_list]
        return enabled

    def run(self, *, skip_art: bool = True, platforms: list[str] = None) -> dict:
        """Execute the full social pipeline.

        Steps:
            1. select_topic() — EIC picks topic (Opus, max 3 retries)
            2. create_brief() — Creative Director expands topic (Sonnet)
            3. create_art() — Art pipeline (Sonnet, optional)
            4. write_drafts() — Per-platform writers (Sonnet, parallel)
            5. review_drafts() — Blind critics (Sonnet, parallel)
            6. validate() — Deterministic policy checks (Python)
            7. humanize() — Remove AI patterns (Sonnet)
            8. expedite() — Final quality gate (Sonnet, FAIL on error)
            9. approve() — Slack approval
            10. post() — Platform API calls with jitter
            11. log_feedback() — Store editorial corrections

        Args:
            skip_art: If True, skip art generation step.
            platforms: Restrict to these platforms. None = all enabled.

        Returns:
            {
                topic, platforms_posted, posts: [{platform, url, id}],
                skipped_platforms, errors, kill_day: bool
            }
        """
        result = {
            "topic": None,
            "platforms_posted": [],
            "posts": [],
            "skipped_platforms": [],
            "errors": [],
            "kill_day": False,
            "gate1_outcome": "unknown",
            "gate1_guidance": "",
            "gate2_outcome": "unknown",
            "gate2_edits": [],
            "expeditor_verdict": "unknown",
            "pending_deferred": [],
            "pending_posted": [],
        }
        target_platforms = self._enabled_platforms(platforms)

        if not target_platforms:
            result["errors"].append("No enabled platforms found")
            return result

        # ── Step 0a: Post any pending (deferred) posts first ──────────
        logger.info("Step 0a: Checking for pending deferred posts")
        pending_posted = self._post_pending(target_platforms)
        if pending_posted:
            result["pending_posted"] = pending_posted
            result["platforms_posted"].extend(
                [p["platform"] for p in pending_posted if not p.get("error")]
            )
            result["posts"].extend(pending_posted)

        # ── Step 0b: Early rate limit check ───────────────────────────
        # Check rate limits BEFORE burning LLM calls on topic/brief/writing.
        # Remove platforms that have already hit their daily post limit.
        rate_limited = []
        for platform in list(target_platforms):
            rate_error = self.policy.validate_post_rate_limit(platform, self.db)
            if rate_error:
                logger.info(
                    f"Early rate limit: skipping {platform} — {rate_error}"
                )
                rate_limited.append(platform)
                target_platforms.remove(platform)
                result["skipped_platforms"].append(platform)

        if not target_platforms:
            logger.info(
                "All platforms rate-limited for today — nothing to do. "
                f"Rate-limited: {rate_limited}"
            )
            return result

        # ── Step 1: Topic selection (Opus, max 3 retries) ─────────────
        logger.info("Step 1: Topic selection (EIC)")
        step1_start = time.monotonic()
        topic = None
        for attempt in range(3):
            try:
                topic = select_topic(
                    db=self.db,
                    user_id=self.user_id,
                    date_str=self.date_str,
                )
                if topic:
                    break
                logger.warning(f"EIC returned no topic (attempt {attempt + 1}/3)")
            except Exception as e:
                logger.error(f"EIC failed (attempt {attempt + 1}/3): {e}")
                result["errors"].append(f"EIC attempt {attempt + 1}: {e}")

        if not topic:
            logger.warning("Kill day — EIC found no viable topics after 3 attempts")
            result["kill_day"] = True
            return result

        result["topic"] = topic
        anchor = topic.get("anchor", topic.get("topic", "unknown"))
        logger.info(f"Step 1 complete: topic='{anchor}', duration={time.monotonic() - step1_start:.1f}s")

        # ── Step 1b: Gate 1 — Topic approval ──────────────────────────
        logger.info("Step 1b: Gate 1 — requesting topic approval")
        try:
            from social.approval import ApprovalGateway
            gateway = ApprovalGateway(self.config)
            gate1 = gateway.request_topic_approval([topic])

            action = gate1.get("action", "go")
            if action == "skip":
                logger.info("Gate 1: User skipped — kill day")
                result["kill_day"] = True
                result["gate1_outcome"] = "rejected"
                return result
            elif action == "go":
                logger.info("Gate 1: Approved")
                result["gate1_outcome"] = "approved"
            elif action == "custom":
                custom = gate1.get("guidance", "") or gate1.get("custom_topic", "")
                logger.info(f"Gate 1: Custom topic — {custom}")
                # Replace the ENTIRE topic with the user's custom content
                # so the brief writer uses it instead of the EIC's analysis
                topic = {
                    "anchor": custom,
                    "topic": custom,
                    "summary": custom,
                    "composite_score": 10.0,
                    "source_urls": [],
                    "custom": True,
                }
                result["gate1_outcome"] = "custom"
                result["gate1_guidance"] = custom
            else:
                logger.info(f"Gate 1: {action}")
                result["gate1_outcome"] = action
        except Exception as e:
            # If approval system fails, auto-approve (don't block the pipeline)
            logger.warning(f"Gate 1 failed (auto-approving): {e}")

        # ── Step 2: Creative brief (Sonnet) ───────────────────────────
        logger.info("Step 2: Creative brief")
        step2_start = time.monotonic()
        try:
            brief = create_brief(
                db=self.db,
                topic=topic,
                date_str=self.date_str,
            )
            logger.info(f"Step 2 complete: duration={time.monotonic() - step2_start:.1f}s")
        except Exception as e:
            logger.error(f"Creative brief failed: {e}")
            result["errors"].append(f"Brief creation: {e}")
            return result

        # ── Step 3: Art pipeline (Sonnet, optional) ───────────────────
        images = {}
        if not skip_art:
            logger.info("Step 3: Art pipeline")
            try:
                images = create_art(
                    db=self.db,
                    brief=brief,
                    date_str=self.date_str,
                    skip_art=False,
                )
                logger.info(f"Art created for {len(images)} platforms")
            except Exception as e:
                logger.warning(f"Art pipeline failed (non-fatal): {e}")
                result["errors"].append(f"Art (non-fatal): {e}")
        else:
            logger.info("Step 3: Art pipeline (skipped)")

        # ── Step 4: Write drafts (Sonnet, parallel per platform) ──────
        logger.info("Step 4: Writing drafts")
        step4_start = time.monotonic()
        try:
            drafts = write_drafts(
                db=self.db,
                brief=brief,
                config=self.config.get("writers", {}),
                platforms=target_platforms,
            )
            logger.info(f"Step 4 complete: {len(drafts) if drafts else 0} drafts, duration={time.monotonic() - step4_start:.1f}s")
        except Exception as e:
            logger.error(f"Draft writing failed: {e}")
            result["errors"].append(f"Writing: {e}")
            return result

        if not drafts:
            logger.error("No drafts produced")
            result["errors"].append("No drafts produced by writers")
            return result

        # ── Step 5: Critic review (Sonnet, parallel per platform) ─────
        logger.info("Step 5: Critic review")
        step5_start = time.monotonic()
        max_critic_rounds = self.config.get("writers", {}).get("critic_max_rounds", 3)

        for round_num in range(1, max_critic_rounds + 1):
            reviews = {}
            with ThreadPoolExecutor(max_workers=len(drafts)) as executor:
                futures = {
                    executor.submit(
                        review_draft, platform,
                        draft.get("content", draft) if isinstance(draft, dict) else draft,
                    ): platform
                    for platform, draft in drafts.items()
                }
                for future in as_completed(futures):
                    platform = futures[future]
                    try:
                        reviews[platform] = future.result()
                    except Exception as e:
                        logger.warning(f"Critic failed for {platform}: {e}")
                        reviews[platform] = {"verdict": "pass", "feedback": ""}

            # Check if any drafts need revision
            needs_revision = {
                p: r for p, r in reviews.items()
                if r.get("verdict") == "revise"
            }

            if not needs_revision:
                logger.info(f"All drafts passed critic review (round {round_num})")
                break

            if round_num < max_critic_rounds:
                logger.info(
                    f"Revising {len(needs_revision)} drafts (round {round_num}/"
                    f"{max_critic_rounds})"
                )
                # Re-write only the drafts that need revision
                try:
                    revised = write_drafts(
                        db=self.db,
                        brief=brief,
                        config=self.config.get("writers", {}),
                        platforms=list(needs_revision.keys()),
                    )
                    drafts.update(revised)
                except Exception as e:
                    logger.warning(f"Revision failed (round {round_num}): {e}")
            else:
                logger.warning(
                    f"Max critic rounds reached, proceeding with current drafts"
                )

        logger.info(f"Step 5 complete: duration={time.monotonic() - step5_start:.1f}s")

        # ── Step 6: Deterministic policy validation + retry ────────────
        logger.info("Step 6: Policy validation")
        step6_start = time.monotonic()
        max_policy_retries = 2
        for policy_attempt in range(max_policy_retries + 1):
            failed_platforms = {}
            for platform in list(drafts.keys()):
                content = drafts[platform]
                if isinstance(content, dict):
                    content = content.get("content", content.get("text", str(content)))

                errors = self.policy.validate_social_post(platform, content)
                if errors:
                    failed_platforms[platform] = errors

            if not failed_platforms:
                logger.info("All drafts passed policy validation")
                break

            if policy_attempt < max_policy_retries:
                # Send violations back to writer for retry
                logger.info(f"Policy retry {policy_attempt + 1}/{max_policy_retries}: {list(failed_platforms.keys())}")
                for platform, errors in failed_platforms.items():
                    content = drafts[platform]
                    if isinstance(content, dict):
                        content = content.get("content", content.get("text", str(content)))

                    fix_prompt = (
                        f"Fix this {platform} post. It has these policy violations:\n"
                        + "\n".join(f"- {e}" for e in errors) + "\n\n"
                        f"Original post:\n{content}\n\n"
                        f"Rewrite to fix ALL violations. Output ONLY the fixed post text."
                    )
                    fixed_output, exit_code = run_claude_prompt(fix_prompt, "writer")
                    if exit_code == 0 and fixed_output.strip():
                        drafts[platform] = fixed_output.strip()
                    else:
                        logger.warning(f"Policy fix failed for {platform}")
            else:
                # Max retries — drop platforms that still fail
                for platform, errors in failed_platforms.items():
                    logger.warning(f"Dropping {platform} after {max_policy_retries} policy retries: {errors}")
                    result["errors"].append(f"Policy ({platform}): {errors}")
                    del drafts[platform]
                    result["skipped_platforms"].append(platform)

        if not drafts:
            logger.error("All drafts failed policy validation")
            result["errors"].append("All drafts failed policy validation")
            return result

        logger.info(f"Step 6 complete: duration={time.monotonic() - step6_start:.1f}s")

        # ── Step 7: Humanize (Sonnet) ─────────────────────────────────
        logger.info("Step 7: Humanize")
        step7_start = time.monotonic()
        for platform in list(drafts.keys()):
            try:
                content = drafts[platform]
                if isinstance(content, dict):
                    text = content.get("content", content.get("text", str(content)))
                else:
                    text = content

                humanized = _humanize(text, platform, self.db)
                if humanized and humanized.strip():
                    drafts[platform] = humanized.strip()
                else:
                    logger.warning(f"Humanizer returned empty for {platform}")
            except Exception as e:
                logger.warning(f"Humanize failed for {platform} (non-fatal): {e}")

        logger.info(f"Step 7 complete: duration={time.monotonic() - step7_start:.1f}s")

        # ── Step 8: Expedite — final quality gate (Sonnet) ────────────
        logger.info("Step 8: Expedite (final quality gate)")
        step8_start = time.monotonic()
        try:
            exp_result = expedite(drafts, brief, images)
            result["expeditor_verdict"] = exp_result.get("verdict", "unknown")
            if exp_result.get("verdict") == "FAIL":
                logger.error(f"Expeditor FAILED: {exp_result.get('notes')}")
                result["errors"].append(f"Expeditor: {exp_result.get('notes')}")
                return result
            logger.info(f"Expeditor: {exp_result.get('verdict')}")
        except Exception as e:
            logger.error(f"Expeditor crashed: {e}")
            result["errors"].append(f"Expeditor crash: {e}")
            return result

        logger.info(f"Step 8 complete: verdict={exp_result.get('verdict', '?')}, duration={time.monotonic() - step8_start:.1f}s")

        # Re-validate after humanize/expedite changes
        for platform in list(drafts.keys()):
            content = drafts[platform]
            if isinstance(content, dict):
                content = content.get("content", content.get("text", str(content)))
            errors = self.policy.validate_social_post(platform, content)
            if errors:
                logger.error(
                    f"Post-expedite policy failure for {platform}: {errors}"
                )
                result["errors"].append(f"Post-expedite policy ({platform}): {errors}")
                del drafts[platform]
                result["skipped_platforms"].append(platform)

        if not drafts:
            logger.error("All drafts failed post-expedite validation")
            return result

        # ── Step 9: Approval (Slack) ──────────────────────────────────
        logger.info("Step 9: Approval")
        step9_start = time.monotonic()
        try:
            approval_response = self.approval.request_draft_approval(drafts, images)
            logger.info(f"Step 9 complete: action={approval_response.get('action', '?')}, duration={time.monotonic() - step9_start:.1f}s")
        except Exception as e:
            logger.error(f"Approval gateway failed: {e}")
            result["errors"].append(f"Approval: {e}")
            return result

        action = approval_response.get("action", "skip")

        if action == "skip":
            logger.info("Drafts rejected by approver")
            result["gate2_outcome"] = "rejected"
            self._log_feedback(drafts, approval_response)
            return result

        # Filter drafts to approved platforms only
        if action == "approve_selected":
            approved_platforms = approval_response.get("platforms", [])
            drafts = {p: d for p, d in drafts.items() if p in approved_platforms}
        # action == "all" means approve everything

        # Apply any inline edits from the approver
        edits = approval_response.get("edits", {})
        for platform, edited_content in edits.items():
            if platform in drafts and edited_content:
                drafts[platform] = edited_content

        result["gate2_outcome"] = "approved"
        result["gate2_edits"] = list(edits.keys()) if edits else []

        if not drafts:
            logger.info("No platforms approved after filtering")
            return result

        # ── Step 10: Post with jitter (or defer to posting window) ────
        step10_start = time.monotonic()
        if self._in_posting_window():
            logger.info(f"Step 10: Posting to {list(drafts.keys())}")
            posted = self._post_with_jitter(drafts, images)
            result["posts"].extend(posted)
            result["platforms_posted"].extend(
                [p["platform"] for p in posted if not p.get("error")]
            )
        else:
            # Outside posting window — defer approved drafts
            logger.info(
                "Step 10: Outside posting window — deferring approved drafts"
            )
            deferred = self._defer_posts(drafts, images)
            result["pending_deferred"] = deferred
            logger.info(
                f"Deferred {len(deferred)} posts to next morning window"
            )
        logger.info(f"Step 10 complete: duration={time.monotonic() - step10_start:.1f}s")

        # ── Step 11: Log feedback and editorial corrections ───────────
        logger.info("Step 11: Logging feedback")
        self._log_feedback(drafts, approval_response)

        successful = len(result["platforms_posted"])
        total = len(drafts)
        logger.info(
            f"Social pipeline complete: {successful}/{total} platforms posted, "
            f"{len(result['errors'])} errors"
        )

        return result

    def _get_posting_window(self) -> tuple[int, int, ZoneInfo]:
        """Get the preferred posting window from config.

        Returns:
            (start_hour, end_hour, timezone) tuple.
        """
        window = self.config.get("preferred_posting_window", {})
        start = window.get("start_hour", 7)
        end = window.get("end_hour", 12)
        tz_name = window.get("timezone", "America/New_York")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            logger.warning(
                f"Invalid timezone '{tz_name}' in posting window config, "
                f"falling back to America/New_York"
            )
            tz = ZoneInfo("America/New_York")
        return start, end, tz

    def _in_posting_window(self) -> bool:
        """Check if the current time is within the preferred posting window.

        If no preferred_posting_window is configured, always returns True
        (backwards-compatible: post anytime).
        """
        if "preferred_posting_window" not in self.config:
            return True

        start_hour, end_hour, tz = self._get_posting_window()
        now = datetime.now(tz)
        return start_hour <= now.hour < end_hour

    def _next_posting_window_start(self) -> str:
        """Calculate the next posting window start time as an ISO string.

        If we're before today's window, returns today at start_hour.
        If we're past today's window, returns tomorrow at start_hour.
        """
        start_hour, end_hour, tz = self._get_posting_window()
        now = datetime.now(tz)

        if now.hour < start_hour:
            # Before today's window — post later today
            next_start = now.replace(
                hour=start_hour, minute=0, second=0, microsecond=0
            )
        else:
            # Past today's window — post tomorrow morning
            next_start = (now + timedelta(days=1)).replace(
                hour=start_hour, minute=0, second=0, microsecond=0
            )

        return next_start.strftime("%Y-%m-%d %H:%M:%S")

    def _defer_posts(self, drafts: dict, images: dict) -> list[dict]:
        """Store approved drafts as pending posts for the next posting window.

        Args:
            drafts: {platform: content_str} dict of approved drafts.
            images: {platform: image_path_or_url} dict.

        Returns:
            List of {platform, pending_id, post_after} dicts.
        """
        post_after = self._next_posting_window_start()
        deferred = []

        for platform, content in drafts.items():
            if isinstance(content, dict):
                content = content.get("content", content.get("text", str(content)))

            image = images.get(platform)
            image_str = str(image) if image else None

            try:
                pending_id = memory.store_pending_post(
                    self.db,
                    platform=platform,
                    content=content,
                    post_after=post_after,
                    image_path=image_str,
                )
                deferred.append({
                    "platform": platform,
                    "pending_id": pending_id,
                    "post_after": post_after,
                })
                logger.info(
                    f"Draft approved, deferring {platform} post to "
                    f"morning window ({post_after})"
                )
            except Exception as e:
                logger.error(f"Failed to defer {platform} post: {e}")

        return deferred

    def _post_pending(self, target_platforms: list[str]) -> list[dict]:
        """Check for and post any pending (deferred) posts that are ready.

        Called at the start of each pipeline run. Posts pending drafts that
        have passed their post_after time and are within the posting window.

        Args:
            target_platforms: List of platform names to check.

        Returns:
            List of {platform, url, id, error} dicts for posted items.
        """
        if not self._in_posting_window():
            return []

        results = []

        for platform in target_platforms:
            pending = memory.get_pending_posts(self.db, platform=platform)

            for post in pending:
                # Re-check rate limit before each pending post
                rate_error = self.policy.validate_post_rate_limit(
                    platform, self.db
                )
                if rate_error:
                    logger.info(
                        f"Rate limit reached for {platform}, "
                        f"skipping remaining pending posts"
                    )
                    break

                client = self._platform_clients.get(platform)
                if not client:
                    continue

                content = post["content"]
                image = post.get("image_path")
                if image:
                    image = Path(image)
                    if not image.exists():
                        image = None

                try:
                    post_result = client.post(content, image_path=image)

                    # Record the post in both tables
                    memory.store_post(
                        self.db,
                        date=self.date_str,
                        platform=platform,
                        content=content,
                        posted=True,
                    )
                    memory.store_engagement(
                        self.db,
                        user_id=self.user_id,
                        platform=platform,
                        engagement_type="post",
                        status="posted",
                    )

                    # Mark the pending post as done
                    memory.mark_pending_posted(self.db, post["id"])

                    results.append({
                        "platform": platform,
                        "url": post_result.get("url"),
                        "id": post_result.get("id"),
                        "error": None,
                        "source": "pending",
                    })
                    logger.info(
                        f"Posted pending {platform} draft "
                        f"(pending_id={post['id']}): "
                        f"{post_result.get('url', 'no url')}"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to post pending {platform} draft "
                        f"(pending_id={post['id']}): {e}"
                    )
                    results.append({
                        "platform": platform,
                        "url": None,
                        "id": None,
                        "error": str(e),
                        "source": "pending",
                    })

        return results

    def _post_with_jitter(self, drafts: dict, images: dict) -> list[dict]:
        """Post to all platforms with random delay between posts.

        Jitter range from config (60-300 seconds default).
        Enforces rate limits via BOTH PolicyEngine.validate_rate_limits
        (engagements table) AND validate_post_rate_limit (social_posts table)
        BEFORE each API call. Both checks now use count_posts_today() which
        queries both tables and takes the higher count.

        Args:
            drafts: {platform: content_str} dict.
            images: {platform: image_path_or_url} dict.

        Returns:
            List of {platform, url, id, error} dicts.
        """
        posting_config = self.policy.rules.get("posting", {})
        jitter_range = posting_config.get("jitter_range_seconds", [60, 300])
        min_delay = posting_config.get("min_delay_seconds", 30)

        results = []
        platform_list = list(drafts.keys())

        # Randomize posting order
        random.shuffle(platform_list)

        for i, platform in enumerate(platform_list):
            content = drafts[platform]
            if isinstance(content, dict):
                content = content.get("content", content.get("text", str(content)))

            image = images.get(platform)

            # Rate limit check BEFORE posting — uses both social_posts
            # and engagements tables via count_posts_today()
            rate_check = self.policy.validate_rate_limits(
                self.db, platform, "post"
            )
            if not rate_check["allowed"]:
                logger.warning(f"Rate limit hit for {platform}: {rate_check['reason']}")
                results.append({
                    "platform": platform,
                    "url": None,
                    "id": None,
                    "error": rate_check["reason"],
                })
                continue

            # Double-check with validate_post_rate_limit (belt and suspenders)
            rate_error = self.policy.validate_post_rate_limit(platform, self.db)
            if rate_error:
                logger.warning(f"Post rate limit hit for {platform}: {rate_error}")
                results.append({
                    "platform": platform,
                    "url": None,
                    "id": None,
                    "error": rate_error,
                })
                continue

            # Post via platform client
            client = self._platform_clients.get(platform)
            if not client:
                results.append({
                    "platform": platform,
                    "url": None,
                    "id": None,
                    "error": f"No client configured for {platform}",
                })
                continue

            try:
                post_result = client.post(content, image_path=image)
                results.append({
                    "platform": platform,
                    "url": post_result.get("url"),
                    "id": post_result.get("id"),
                    "error": None,
                })

                # Store in memory — IMMEDIATELY after posting so subsequent
                # rate limit checks within this same run will see it
                memory.store_post(
                    self.db,
                    date=self.date_str,
                    platform=platform,
                    content=content,
                    posted=True,
                )

                # Log as engagement action for rate limit tracking
                memory.store_engagement(
                    self.db,
                    user_id=self.user_id,
                    platform=platform,
                    engagement_type="post",
                    status="posted",
                )

                logger.info(
                    f"Posted to {platform}: {post_result.get('url', 'no url')}"
                )

            except Exception as e:
                logger.error(f"Failed to post to {platform}: {e}")
                results.append({
                    "platform": platform,
                    "url": None,
                    "id": None,
                    "error": str(e),
                })

            # Jitter between posts (skip after last one)
            if i < len(platform_list) - 1:
                delay = random.uniform(
                    max(min_delay, jitter_range[0]),
                    jitter_range[1],
                )
                logger.info(f"Jitter delay: {delay:.0f}s before next post")
                time.sleep(delay)

        return results

    def _log_feedback(self, drafts: dict, approval_response: dict):
        """Store editorial feedback and corrections from the approval gate.

        Records Gate 2 actions for each platform, and stores any inline edits
        as editorial corrections for future learning.
        """
        action = approval_response.get("action", "skip")
        edits = approval_response.get("edits", {})

        for platform in drafts:
            original = drafts[platform]
            if isinstance(original, dict):
                original = original.get("content", original.get("text", str(original)))

            final = edits.get(platform, original)
            if isinstance(final, dict):
                final = final.get("content", final.get("text", str(final)))

            gate2_action = action
            if action == "approve_selected":
                approved_platforms = approval_response.get("platforms", [])
                gate2_action = "approved" if platform in approved_platforms else "skip"
            elif action == "all":
                gate2_action = "approved"

            try:
                memory.store_social_feedback(
                    self.db,
                    date=self.date_str,
                    platform=platform,
                    action=gate2_action,
                    original=original,
                    final=final,
                )
            except Exception as e:
                logger.warning(f"Failed to store feedback for {platform}: {e}")

            # Store editorial correction if content was edited
            if (
                gate2_action == "approved"
                and original
                and final
                and original.strip() != final.strip()
            ):
                try:
                    memory.store_correction(
                        self.db,
                        platform=platform,
                        original_text=original,
                        approved_text=final,
                        reason="Gate 2 inline edit",
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to store correction for {platform}: {e}"
                    )

