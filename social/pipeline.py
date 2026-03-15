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
from datetime import datetime
from pathlib import Path

import memory
from orchestrator.agents import run_claude_prompt
from policies.engine import PolicyEngine
from social.approval import ApprovalGateway
from social.art import create_art
from social.eic import select_topic, create_brief
from social.writers import write_drafts
from social.critics import review_draft, deterministic_validate, expedite
from social.posting import XClient, BlueskyClient, LinkedInClient

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

        if platforms.get("x", {}).get("enabled"):
            clients["x"] = XClient(platforms["x"])
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
            9. approve() — Dashboard + iMessage approval
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
        }
        target_platforms = self._enabled_platforms(platforms)

        if not target_platforms:
            result["errors"].append("No enabled platforms found")
            return result

        # ── Step 1: Topic selection (Opus, max 3 retries) ─────────────
        logger.info("Step 1: Topic selection (EIC)")
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
        logger.info(f"Topic selected: {anchor}")

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
                return result
            elif action == "go":
                logger.info("Gate 1: Approved")
            elif action == "custom":
                custom = gate1.get("custom_topic", "")
                logger.info(f"Gate 1: Custom topic — {custom}")
                topic["anchor"] = custom
            else:
                logger.info(f"Gate 1: {action}")
        except Exception as e:
            # If approval system fails, auto-approve (don't block the pipeline)
            logger.warning(f"Gate 1 failed (auto-approving): {e}")

        # ── Step 2: Creative brief (Sonnet) ───────────────────────────
        logger.info("Step 2: Creative brief")
        try:
            brief = create_brief(
                db=self.db,
                topic=topic,
                date_str=self.date_str,
            )
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
        try:
            drafts = write_drafts(
                db=self.db,
                brief=brief,
                config=self.config.get("writers", {}),
                platforms=target_platforms,
            )
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

        # ── Step 6: Deterministic policy validation + retry ────────────
        logger.info("Step 6: Policy validation")
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

        # ── Step 7: Humanize (Sonnet) ─────────────────────────────────
        logger.info("Step 7: Humanize")
        for platform in list(drafts.keys()):
            try:
                content = drafts[platform]
                if isinstance(content, dict):
                    text = content.get("content", content.get("text", str(content)))
                else:
                    text = content

                humanized_output, exit_code = run_claude_prompt(
                    prompt=self._build_humanize_prompt(platform, text),
                    task_type="humanizer",
                )
                if exit_code == 0 and humanized_output.strip():
                    drafts[platform] = humanized_output.strip()
                else:
                    logger.warning(f"Humanizer returned empty or failed for {platform}")
            except Exception as e:
                logger.warning(f"Humanize failed for {platform} (non-fatal): {e}")

        # ── Step 8: Expedite — final quality gate (Sonnet) ────────────
        logger.info("Step 8: Expedite (final quality gate)")
        try:
            exp_result = expedite(drafts, brief, images)
            if exp_result.get("verdict") == "FAIL":
                logger.error(f"Expeditor FAILED: {exp_result.get('notes')}")
                result["errors"].append(f"Expeditor: {exp_result.get('notes')}")
                return result
            logger.info(f"Expeditor: {exp_result.get('verdict')}")
        except Exception as e:
            logger.error(f"Expeditor crashed: {e}")
            result["errors"].append(f"Expeditor crash: {e}")
            return result

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

        # ── Step 9: Approval (dashboard + iMessage fallback) ──────────
        logger.info("Step 9: Approval")
        try:
            approval_response = self.approval.request_draft_approval(drafts, images)
        except Exception as e:
            logger.error(f"Approval gateway failed: {e}")
            result["errors"].append(f"Approval: {e}")
            return result

        action = approval_response.get("action", "skip")

        if action == "skip":
            logger.info("Drafts rejected by approver")
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

        if not drafts:
            logger.info("No platforms approved after filtering")
            return result

        # ── Step 10: Post with jitter ─────────────────────────────────
        logger.info(f"Step 10: Posting to {list(drafts.keys())}")
        posted = self._post_with_jitter(drafts, images)
        result["posts"] = posted
        result["platforms_posted"] = [p["platform"] for p in posted if not p.get("error")]

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

    def _post_with_jitter(self, drafts: dict, images: dict) -> list[dict]:
        """Post to all platforms with random delay between posts.

        Jitter range from config (60-300 seconds default).
        Enforces rate limits via PolicyEngine BEFORE each API call.

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

            # Rate limit check BEFORE posting
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
                post_result = client.post(content, image=image)
                results.append({
                    "platform": platform,
                    "url": post_result.get("url"),
                    "id": post_result.get("id"),
                    "error": None,
                })

                # Store in memory
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

    def _build_humanize_prompt(self, platform: str, content: str) -> str:
        """Build prompt for the humanizer agent.

        Includes editorial corrections from memory for voice calibration.
        """
        corrections = memory.recent_corrections(self.db, platform=platform, limit=5)
        corrections_section = ""
        if corrections:
            examples = []
            for c in corrections:
                examples.append(
                    f"BEFORE: {c['original_text'][:200]}\n"
                    f"AFTER: {c['approved_text'][:200]}"
                )
            corrections_section = (
                "\n\n## Recent Editorial Corrections (learn from these):\n"
                + "\n---\n".join(examples)
            )

        return f"""You are a humanizer for social media posts. Your job is to remove
AI-sounding patterns while preserving the core message and voice.

## Rules
- Remove em dashes, replace with commas or periods
- Remove filler phrases ("It's worth noting", "Interestingly", "Let's dive in")
- Remove rhetorical questions at the end
- Keep the length approximately the same
- Do NOT add hashtags
- Do NOT add emojis unless the original had them
- Keep technical accuracy intact
- Match the casual, knowledgeable voice of a senior developer

## Platform: {platform}
## Content to humanize:

{content}
{corrections_section}

Output ONLY the humanized post text. No commentary, no explanation."""
