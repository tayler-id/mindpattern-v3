"""Engagement pipeline — find, draft, approve, post replies.

Discovers relevant conversations on Bluesky (and optionally X/LinkedIn),
drafts replies using the brand voice, runs them through approval, and
posts with jitter. All engagement actions are tracked in memory.

Key difference from v1/v2: Python does the platform API searching directly
(via BlueskyClient.search()), then passes results to the LLM for query
generation and ranking. This replaces the broken v3 approach of asking
run_claude_prompt() to somehow search APIs it has no access to.

Flow:
    1. LLM generates search queries from today's research findings
    2. Python executes those queries via platform API clients
    3. Python filters: follower count, like count, age, already-engaged
    4. Python checks Bluesky relationships (skip already-connected)
    5. LLM ranks and selects top candidates
    6. LLM drafts replies with voice guide
    7. Rate limit check + approval gate
    8. Post replies + auto-follow
"""

import json
import logging
import random
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import memory
from orchestrator.agents import run_claude_prompt
from policies.engine import PolicyEngine
from social.approval import ApprovalGateway
from social.posting import BlueskyClient, LinkedInClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


# ── LinkedIn search via Jina Reader ───────────────────────────────────────


def search_via_jina(
    query: str, max_results: int = 10
) -> list[dict]:
    """Search LinkedIn posts via Jina Reader's search endpoint.

    Uses Jina's ``s.jina.ai`` search endpoint with a ``site:linkedin.com``
    filter to discover LinkedIn posts matching the query. Parses the
    markdown response to extract URLs and content, then normalizes results
    into the same dict format that BlueskyClient.search() returns.

    Args:
        query: Search query string (e.g. "AI agents developer tools").
        max_results: Maximum number of results to return.

    Returns:
        List of normalized post dicts with keys: url, text, author_handle,
        author_name, followers_count, like_count, reply_count, platform.
        Returns empty list on any failure.
    """
    search_query = f"{query} site:linkedin.com"

    try:
        result = subprocess.run(
            ["curl", "-s", f"https://s.jina.ai/{quote(search_query)}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Jina search timed out for query: %s", query)
        return []
    except Exception as e:
        logger.warning("Jina search failed for query '%s': %s", query, e)
        return []

    if result.returncode != 0 or not result.stdout.strip():
        logger.warning(
            "Jina search returned error (rc=%d) for query: %s",
            result.returncode,
            query,
        )
        return []

    return _parse_jina_results(result.stdout, max_results)


def _parse_jina_results(markdown: str, max_results: int) -> list[dict]:
    """Parse Jina Reader markdown output into normalized post dicts.

    Jina returns search results as markdown with sections like:
        ## [1] Title
        **URL:** https://linkedin.com/posts/...
        Author Name - Role

        Post content...

    Args:
        markdown: Raw markdown from Jina Reader.
        max_results: Cap on results to return.

    Returns:
        List of normalized post dicts.
    """
    results = []

    # Split on section headers (## [N] ...)
    sections = re.split(r"^## \[\d+\]\s*", markdown, flags=re.MULTILINE)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Extract URL — look for **URL:** or bare LinkedIn URLs
        url_match = re.search(
            r"\*\*URL:\*\*\s*(https?://[^\s]+linkedin\.com/[^\s]+)",
            section,
        )
        if not url_match:
            # Try bare LinkedIn URL
            url_match = re.search(
                r"(https?://(?:www\.)?linkedin\.com/posts/[^\s\)]+)",
                section,
            )
        if not url_match:
            continue

        url = url_match.group(1).rstrip(".,;:!?")

        # Extract author handle from URL: /posts/username_slug
        handle_match = re.search(
            r"linkedin\.com/posts/([a-zA-Z0-9_-]+)", url
        )
        author_handle = handle_match.group(1) if handle_match else ""

        # Extract title (first line of section)
        lines = section.split("\n")
        title = lines[0].strip() if lines else ""

        # Extract author name from lines after URL
        # Pattern: "Author Name - Role at Company"
        author_name = ""
        for line in lines[1:5]:
            line = line.strip()
            if line.startswith("**URL:**") or not line:
                continue
            # Skip markdown formatting lines
            if line.startswith("---"):
                break
            # First non-URL, non-empty line after title is likely author
            if not author_name and line and not line.startswith("*"):
                author_name = line.split(" - ")[0].strip()
                break

        # Extract content: everything after the metadata lines
        content_lines = []
        past_metadata = False
        for line in lines:
            if past_metadata:
                if line.strip() == "---":
                    break
                content_lines.append(line)
            elif line.strip() == "" and len(content_lines) == 0:
                # Empty line after metadata signals start of content
                past_metadata = True

        text = "\n".join(content_lines).strip()
        if not text:
            # Fallback: use title as text
            text = title

        if not text:
            continue

        results.append(
            {
                "url": url,
                "text": text,
                "author_handle": author_handle,
                "author_name": author_name or author_handle,
                "followers_count": 0,  # Unknown from search
                "like_count": 0,  # Unknown from search
                "reply_count": 0,  # Unknown from search
                "platform": "linkedin",
            }
        )

        if len(results) >= max_results:
            break

    return results


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
        self._linkedin_drafts_dir = PROJECT_ROOT / "data" / "social-drafts"

    def _init_platform_clients(self) -> dict:
        """Initialize API clients for engagement-enabled platforms only.

        Uses engagement.platforms list from config if present,
        otherwise falls back to all enabled platforms.

        Note: LinkedIn is excluded from platform clients for engagement
        because LinkedInClient has no search() or reply() methods.
        LinkedIn engagement uses search_via_jina() for discovery and
        draft-only mode for replies.
        """
        clients = {}
        platforms = self.config.get("platforms", {})
        engagement_platforms = self.engagement_config.get("platforms")

        if platforms.get("bluesky", {}).get("enabled"):
            if engagement_platforms is None or "bluesky" in engagement_platforms:
                clients["bluesky"] = BlueskyClient(platforms["bluesky"])
        # LinkedIn is intentionally excluded from platform clients for
        # engagement. It uses Jina Reader search and draft-only posting.

        return clients

    def run(self, *, dry_run: bool = False) -> dict:
        """Execute the engagement pipeline.

        Steps:
            1. Find conversations matching today's research (API search + LLM ranking)
            2. Filter: skip already-engaged authors (memory.check_engagement)
            3. Draft replies with voice guide + editorial corrections (Sonnet)
            4. Rate limit check (PolicyEngine, enforced not advisory)
            5. Approval gate (ApprovalGateway)
            6. Post replies + auto-follow (with jitter)
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

    # ── Phase 1a: Generate search queries from research findings ──────

    def _generate_search_queries(self, topics: list[str]) -> list[str]:
        """Use LLM to generate specific search queries from research topics.

        Takes broad research finding titles and produces focused queries
        optimized for Bluesky's search API.

        Args:
            topics: List of research finding titles.

        Returns:
            List of search query strings.
        """
        queries_per_platform = self.engagement_config.get(
            "search_queries_per_platform", 8
        )

        topics_list = "\n".join(f"- {t}" for t in topics)

        prompt = f"""You are generating search queries for finding social media conversations.

## Research Topics
{topics_list}

## Task
Generate {queries_per_platform} specific search queries optimized for Bluesky's
post search API. Each query should find conversations where a knowledgeable
reply would add value.

## Query Guidelines
- Be specific: "Claude Code MCP" not "AI tools"
- Use terms people actually post about
- Mix: some topic-specific, some broader community terms
- Include tool/product names when relevant
- Avoid overly academic language

## Output Format
Output ONLY valid JSON:
{{
  "queries": ["query1", "query2", ...]
}}"""

        output, exit_code = run_claude_prompt(
            prompt=prompt,
            task_type="engagement_finder",
        )

        if exit_code != 0 or not output:
            logger.warning("Query generation failed, using topic titles as fallback")
            return topics[:queries_per_platform]

        try:
            data = json.loads(output.strip())
            queries = data.get("queries", [])
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*"queries"[\s\S]*\}', output)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    queries = data.get("queries", [])
                except json.JSONDecodeError:
                    queries = []

        if not queries:
            logger.warning("No queries parsed, using topic titles as fallback")
            return topics[:queries_per_platform]

        logger.info(f"Generated {len(queries)} search queries")
        return queries[:queries_per_platform]

    # ── Phase 1b: Execute searches via platform API clients ───────────

    def _search_platform(
        self, platform: str, client, queries: list[str]
    ) -> list[dict]:
        """Execute search queries against a single platform's API.

        Args:
            platform: Platform name (e.g. "bluesky").
            client: Platform API client instance (e.g. BlueskyClient).
            queries: List of search query strings.

        Returns:
            List of raw post dicts from the platform API.
        """
        all_posts = []
        seen_uris = set()

        for query in queries:
            try:
                posts = client.search(query, max_results=50)
                for p in posts:
                    # Dedup by URI/ID
                    uri = p.get("uri") or p.get("id", "")
                    if uri and uri not in seen_uris:
                        seen_uris.add(uri)
                        all_posts.append(p)
            except Exception as e:
                logger.warning(f"Search failed on {platform} for '{query}': {e}")

            # Small delay between queries to avoid rate limits
            time.sleep(random.uniform(0.5, 1.5))

        logger.info(
            f"Searched {platform}: {len(queries)} queries, "
            f"{len(all_posts)} unique posts"
        )
        return all_posts

    # ── Phase 1c: Filter posts by hard criteria ───────────────────────

    def _filter_posts(
        self, posts: list[dict], platform: str
    ) -> list[dict]:
        """Apply hard filters to raw search results.

        Removes posts that don't meet minimum engagement, follower count,
        or age criteria. Also removes link-only posts and our own posts.

        Args:
            posts: Raw post dicts from platform search.
            platform: Platform name.

        Returns:
            Filtered list of post dicts.
        """
        min_likes = self.engagement_config.get("min_likes", 0)
        max_likes = self.engagement_config.get("max_likes", 5000)
        min_followers = self.engagement_config.get("min_follower_count", 10)

        # Get our own handle to skip self-posts
        our_handle = ""
        platform_config = self.config.get("platforms", {}).get(platform, {})
        if platform == "bluesky":
            our_handle = platform_config.get("handle", "")

        filtered = []
        for p in posts:
            # Skip our own posts
            author_handle = p.get("author_handle", p.get("author", ""))
            if our_handle and author_handle == our_handle:
                continue

            # Follower count check — skip filter if API returned 0 (unknown, not zero)
            followers = p.get("followers_count", p.get("followers", 0))
            if followers > 0 and followers < min_followers:
                continue

            # Like count check
            likes = p.get("like_count", p.get("likes", 0))
            if likes < min_likes or likes > max_likes:
                continue

            # Skip posts with no text content (link-only, images-only)
            text = p.get("text", "")
            if len(text.strip()) < 20:
                continue

            # Age check: skip posts older than 48 hours
            created_at = p.get("created_at", "")
            if created_at:
                try:
                    post_time = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                    age_hours = (
                        datetime.now(timezone.utc) - post_time
                    ).total_seconds() / 3600
                    if age_hours > 48:
                        continue
                except (ValueError, TypeError):
                    pass  # Can't parse date, keep the post

            filtered.append(p)

        logger.info(
            f"Filtered {platform}: {len(posts)} -> {len(filtered)} posts "
            f"(min_likes={min_likes}, min_followers={min_followers})"
        )
        return filtered

    # ── Phase 1d: Check connections (skip already-following) ──────────

    def _filter_already_connected(
        self, posts: list[dict], platform: str
    ) -> list[dict]:
        """Remove posts from authors we already follow.

        Uses platform API to check relationship status in batch.

        Args:
            posts: Filtered post dicts.
            platform: Platform name.

        Returns:
            Posts from authors we're NOT already connected to.
        """
        client = self._platform_clients.get(platform)

        if platform == "bluesky" and isinstance(client, BlueskyClient):
            # Collect unique DIDs
            dids = list({
                p["author_did"]
                for p in posts
                if p.get("author_did")
            })

            if not dids:
                return posts

            try:
                relationships = client.get_relationships(dids)
            except Exception as e:
                logger.warning(
                    f"Relationship check failed on {platform}: {e}. "
                    f"Proceeding without filtering."
                )
                return posts

            not_connected = []
            already_following = 0
            for p in posts:
                did = p.get("author_did", "")
                rel = relationships.get(did, {})
                if rel.get("following"):
                    already_following += 1
                    continue
                not_connected.append(p)

            if already_following:
                logger.info(
                    f"Filtered out {already_following} already-followed authors "
                    f"on {platform}"
                )
            return not_connected

        # For other platforms, skip connection check (X API is expensive)
        return posts

    # ── Phase 1e: LLM ranks and selects top candidates ────────────────

    def _rank_candidates(
        self, posts: list[dict], topics: list[str], platform: str
    ) -> list[dict]:
        """Use LLM to rank posts by relevance and reply-worthiness.

        Passes the raw search results and research topics to the LLM,
        which scores and selects the best candidates.

        Args:
            posts: Filtered post dicts.
            topics: Research topic titles for context.
            platform: Platform name.

        Returns:
            Ranked list of candidate dicts in engagement pipeline format.
        """
        candidates_per_platform = self.engagement_config.get(
            "candidates_per_platform", 20
        )

        if not posts:
            return []

        # Truncate to avoid token limits (max 100 posts for ranking)
        posts_for_ranking = posts[:100]

        # Format posts for the LLM prompt
        posts_json = json.dumps(
            [
                {
                    "index": i,
                    "text": p.get("text", "")[:300],
                    "author": p.get("author_handle", p.get("author", "")),
                    "author_name": p.get("author_name", ""),
                    "likes": p.get("like_count", p.get("likes", 0)),
                    "replies": p.get("reply_count", p.get("replies", 0)),
                    "followers": p.get("followers_count", p.get("followers", 0)),
                }
                for i, p in enumerate(posts_for_ranking)
            ],
            indent=2,
        )

        topics_list = "\n".join(f"- {t}" for t in topics)

        prompt = f"""You are ranking social media posts for engagement.

## Today's Research Topics
{topics_list}

## Posts to Rank ({platform})
{posts_json}

## Task
Select the top {candidates_per_platform} posts that are best for engagement.

## Scoring Criteria
1. **Topic relevance** (1-5): How well does the post connect to today's research?
2. **Reply-worthiness** (1-5): Is there a clear opening for a substantive reply?
3. **Person signal** (1-3): Is the author a builder, researcher, or thought leader?
4. **Engagement sweet spot** (1-3): Active discussion but not buried (5-50 likes ideal)

Avoid: political posts, drama threads, promotional content, link-only posts.
Prefer: questions, opinions we can add to, technical discussions.

## Output Format
Output ONLY valid JSON:
{{
  "selected": [
    {{
      "index": 0,
      "relevance": 4,
      "reply_worthiness": 5,
      "person_signal": 2,
      "engagement_score": 3,
      "total_score": 14,
      "topic_connection": "Why this post connects to today's research"
    }}
  ]
}}

Return up to {candidates_per_platform} posts, sorted by total_score descending."""

        output, exit_code = run_claude_prompt(
            prompt=prompt,
            task_type="engagement_finder",
        )

        if exit_code != 0 or not output:
            logger.warning(
                f"Ranking failed for {platform}, returning top posts by likes"
            )
            # Fallback: just return top posts by like count
            posts_for_ranking.sort(
                key=lambda p: p.get("like_count", p.get("likes", 0)),
                reverse=True,
            )
            return [
                self._post_to_candidate(p, platform)
                for p in posts_for_ranking[:candidates_per_platform]
            ]

        try:
            data = json.loads(output.strip())
            selected = data.get("selected", [])
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*"selected"[\s\S]*\}', output)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    selected = data.get("selected", [])
                except json.JSONDecodeError:
                    selected = []

        if not selected:
            logger.warning(f"No ranked candidates for {platform}, using fallback")
            posts_for_ranking.sort(
                key=lambda p: p.get("like_count", p.get("likes", 0)),
                reverse=True,
            )
            return [
                self._post_to_candidate(p, platform)
                for p in posts_for_ranking[:candidates_per_platform]
            ]

        # Map ranked indices back to post data
        candidates = []
        for s in selected[:candidates_per_platform]:
            idx = s.get("index", -1)
            if 0 <= idx < len(posts_for_ranking):
                post = posts_for_ranking[idx]
                candidate = self._post_to_candidate(post, platform)
                candidate["relevance"] = s.get("total_score", 0) / 16.0  # Normalize to 0-1
                candidate["relevance_score"] = s.get("relevance", 0)
                candidate["reply_worthiness"] = s.get("reply_worthiness", 0)
                candidate["person_signal"] = s.get("person_signal", 0)
                candidate["total_score"] = s.get("total_score", 0)
                candidate["topic_connection"] = s.get("topic_connection", "")
                candidates.append(candidate)

        logger.info(f"Ranked {len(candidates)} candidates for {platform}")
        return candidates

    def _post_to_candidate(self, post: dict, platform: str) -> dict:
        """Convert a raw platform post dict to the engagement candidate format.

        Normalizes field names across platforms into the unified candidate
        schema used by the rest of the pipeline.
        """
        if platform == "bluesky":
            handle = post.get("author_handle", "")
            uri = post.get("uri", "")
            rkey = uri.split("/")[-1] if uri else ""
            return {
                "platform": "bluesky",
                "post_id": uri,
                "post_cid": post.get("cid", ""),
                "author": handle,
                "author_id": post.get("author_did", ""),
                "content": post.get("text", ""),
                "target_post_url": post.get("url", f"https://bsky.app/profile/{handle}/post/{rkey}"),
                "target_author": post.get("author_name", handle),
                "target_author_id": post.get("author_did", ""),
                "target_content": post.get("text", ""),
                "followers": post.get("followers_count", 0),
                "likes": post.get("like_count", 0),
                "replies": post.get("reply_count", 0),
                "relevance": 0,
                "our_reply": "",
            }
        else:
            # Generic fallback
            return {
                "platform": platform,
                "post_id": post.get("id", post.get("uri", "")),
                "post_cid": post.get("cid", ""),
                "author": post.get("author", ""),
                "author_id": post.get("author_id", post.get("author_did", "")),
                "content": post.get("text", ""),
                "target_post_url": post.get("url", ""),
                "target_author": post.get("author_name", post.get("author", "")),
                "target_author_id": post.get("author_id", post.get("author_did", "")),
                "target_content": post.get("text", ""),
                "followers": post.get("followers_count", 0),
                "likes": post.get("like_count", 0),
                "replies": post.get("reply_count", 0),
                "relevance": 0,
                "our_reply": "",
            }

    # ── _find_candidates: the main search orchestrator ────────────────

    def _find_candidates(self, date_str: str) -> list[dict]:
        """Search platforms for engagement candidates using API + LLM ranking.

        This is the fixed version that actually works. Instead of asking an LLM
        to magically search social media (which it can't), we:
        1. Use LLM to generate good search queries from today's research
        2. Execute those queries directly via platform API clients
        3. Filter by hard criteria (followers, likes, age, connections)
        4. Use LLM to rank and select the best candidates

        Args:
            date_str: Today's date (YYYY-MM-DD).

        Returns:
            List of candidate dicts ready for reply drafting.
        """
        # Get today's research context
        context = memory.get_context(self.db, "orchestrator", date_str)
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

        # Step 1: Generate search queries from research topics
        logger.info(f"Generating search queries from {len(topics)} topics")
        queries = self._generate_search_queries(topics)
        logger.info(f"Generated {len(queries)} search queries: {queries}")

        # Step 2: Execute searches on each platform
        all_candidates = []
        engagement_platforms = self.engagement_config.get("platforms", [])

        for platform, client in self._platform_clients.items():
            logger.info(f"Searching {platform} with {len(queries)} queries...")

            # Search
            raw_posts = self._search_platform(platform, client, queries)
            if not raw_posts:
                logger.info(f"No posts found on {platform}")
                continue

            # Filter by hard criteria
            filtered = self._filter_posts(raw_posts, platform)
            if not filtered:
                logger.info(f"All posts filtered out on {platform}")
                continue

            # Filter already-connected authors
            not_connected = self._filter_already_connected(filtered, platform)
            if not not_connected:
                logger.info(
                    f"All remaining posts from already-connected authors on {platform}"
                )
                continue

            # Rank and select candidates
            candidates = self._rank_candidates(not_connected, topics, platform)
            all_candidates.extend(candidates)

            logger.info(
                f"{platform}: {len(raw_posts)} raw -> {len(filtered)} filtered -> "
                f"{len(not_connected)} not connected -> {len(candidates)} ranked"
            )

        # Step 2b: LinkedIn via Jina Reader search (no native search API)
        # If "linkedin" is in engagement platforms but NOT in _platform_clients
        # (LinkedInClient doesn't have search()), use search_via_jina() instead.
        if "linkedin" in engagement_platforms and "linkedin" not in self._platform_clients:
            logger.info("Searching LinkedIn via Jina Reader search...")
            all_linkedin_posts = []
            seen_urls = set()

            for query in queries:
                try:
                    posts = search_via_jina(query, max_results=10)
                    for p in posts:
                        url = p.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_linkedin_posts.append(p)
                except Exception as e:
                    logger.warning(f"Jina search failed for '{query}': {e}")

                time.sleep(random.uniform(0.5, 1.5))

            if all_linkedin_posts:
                logger.info(
                    f"LinkedIn via Jina: {len(all_linkedin_posts)} unique posts"
                )

                # Filter by hard criteria
                filtered = self._filter_posts(all_linkedin_posts, "linkedin")
                if filtered:
                    # Rank and select candidates
                    candidates = self._rank_candidates(
                        filtered, topics, "linkedin"
                    )
                    all_candidates.extend(candidates)

                    logger.info(
                        f"linkedin: {len(all_linkedin_posts)} raw -> "
                        f"{len(filtered)} filtered -> {len(candidates)} ranked"
                    )
                else:
                    logger.info("All LinkedIn posts filtered out")
            else:
                logger.info("No LinkedIn posts found via Jina search")

        logger.info(f"Total candidates across all platforms: {len(all_candidates)}")
        return all_candidates

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
                    "topic_connection": c.get("topic_connection", ""),
                    "max_reply_chars": platform_limits.get(c.get("platform"), 280),
                }
                for i, c in enumerate(candidates)
            ],
            indent=2,
        )

        prompt = f"""You are an engagement reply writer for MindPattern, a technical AI newsletter.

## Voice Guide
- Casual, knowledgeable tone of a senior developer
- Add genuine value (insight, experience, data) -- never generic "great point!"
- No hashtags, no emojis unless the conversation calls for it
- No em dashes. Use commas or periods instead.
- Keep replies concise -- match the platform's vibe
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

        LinkedIn is draft-only: saves the reply to a JSON file and sends an
        iMessage notification for manual posting, since we don't have LinkedIn
        Comments API access.

        Args:
            candidate: Dict with platform, post_id, author_id, our_reply,
                       should_follow, etc.

        Returns:
            {reply_posted: bool, follow_success: bool, draft_saved: bool,
             error: str | None}
        """
        platform = candidate.get("platform", "")
        post_id = candidate.get("post_id", "")
        post_cid = candidate.get("post_cid", "")
        author_id = candidate.get("author_id", "")
        our_reply = candidate.get("our_reply", "")
        should_follow = candidate.get("should_follow", False)

        # ── LinkedIn: draft-only mode ─────────────────────────────────
        if platform == "linkedin":
            return self._draft_linkedin_engagement(candidate)

        client = self._platform_clients.get(platform)
        if not client:
            return {
                "reply_posted": False,
                "follow_success": False,
                "draft_saved": False,
                "error": f"No client for {platform}",
            }

        result = {
            "reply_posted": False,
            "follow_success": False,
            "draft_saved": False,
            "error": None,
        }

        # Post the reply -- use correct API signatures per platform
        try:
            if platform == "bluesky":
                reply_result = client.reply(
                    content=our_reply,
                    parent_uri=post_id,
                    parent_cid=post_cid,
                )
            else:
                logger.warning(f"Reply not supported for platform: {platform}")
                return result

            if reply_result.get("success"):
                result["reply_posted"] = True
            else:
                result["error"] = reply_result.get("error", "Reply failed")

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
                status="posted" if result["reply_posted"] else "failed",
            )

            if result["reply_posted"]:
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
        if should_follow and author_id and result["reply_posted"]:
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

    def _draft_linkedin_engagement(self, candidate: dict) -> dict:
        """Save a LinkedIn engagement reply as a draft for manual posting.

        LinkedIn Comments API is not available, so we save the drafted reply
        to a JSON file and send an iMessage notification so the user can
        copy-paste the reply manually.

        Args:
            candidate: Engagement candidate dict with our_reply, target info.

        Returns:
            {reply_posted: False, follow_success: False, draft_saved: bool,
             error: str | None}
        """
        result = {
            "reply_posted": False,
            "follow_success": False,
            "draft_saved": False,
            "error": None,
        }

        our_reply = candidate.get("our_reply", "")
        author_id = candidate.get("author_id", "")

        if not our_reply:
            result["error"] = "No reply text to draft"
            return result

        # Save draft to JSON file
        try:
            self._linkedin_drafts_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            draft_file = self._linkedin_drafts_dir / f"engagement-linkedin-{timestamp}.json"

            draft_data = {
                "platform": "linkedin",
                "target_post_url": candidate.get("target_post_url", ""),
                "target_author": candidate.get("author", ""),
                "target_author_id": author_id,
                "target_content": candidate.get("content", ""),
                "our_reply": our_reply,
                "relevance": candidate.get("relevance", 0),
                "topic_connection": candidate.get("topic_connection", ""),
                "drafted_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending_manual_post",
            }

            with open(draft_file, "w") as f:
                json.dump(draft_data, f, indent=2)

            result["draft_saved"] = True
            logger.info(
                f"LinkedIn engagement draft saved: {draft_file.name} "
                f"(reply to @{candidate.get('author', '?')})"
            )

        except Exception as e:
            result["error"] = f"Failed to save LinkedIn draft: {e}"
            logger.error(f"LinkedIn draft save failed: {e}")
            return result

        # Send iMessage notification for manual posting
        try:
            target_url = candidate.get("target_post_url", "")
            author = candidate.get("author", "unknown")
            message = (
                f"LinkedIn Engagement Draft\n\n"
                f"Reply to @{author}:\n"
                f"{target_url}\n\n"
                f"Draft reply:\n{our_reply}\n\n"
                f"(Copy and paste this reply on LinkedIn manually)"
            )
            self.approval._imessage_send(self.approval.phone, message)
        except Exception as e:
            logger.warning(f"iMessage notification failed for LinkedIn draft: {e}")
            # Don't fail the whole operation if iMessage fails

        # Log as drafted in memory
        memory.store_engagement(
            self.db,
            user_id=self.user_id,
            platform="linkedin",
            engagement_type="reply",
            target_post_url=candidate.get("target_post_url"),
            target_author=candidate.get("author"),
            target_author_id=author_id,
            target_content=candidate.get("content"),
            our_reply=our_reply,
            status="drafted",
        )

        return result
