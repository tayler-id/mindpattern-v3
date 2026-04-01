"""Social media platform API clients — X, Bluesky, LinkedIn.

Replaces v2's social-post.py (subprocess curl calls) with proper
requests-based clients, OAuth1 for X, session-cached JWT for Bluesky,
and exponential-backoff retry on all API calls.

All public methods return dicts with a `success` boolean.
"""

from __future__ import annotations

import io
import logging
import random
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests_oauthlib import OAuth1

log = logging.getLogger(__name__)


# ── Shared helpers ───────────────────────────────────────────────────────


def keychain_get(service_name: str) -> str | None:
    """Read a secret from macOS Keychain.

    Returns the secret string, or None if the lookup times out.
    Raises RuntimeError if the key is not found (non-timeout failure).
    """
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service_name, "-w"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        log.error("Keychain lookup timed out for '%s'", service_name)
        return None
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not read '{service_name}' from macOS Keychain: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _api_call_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    timeout: int = 30,
    **kwargs: Any,
) -> requests.Response:
    """Make an HTTP request with exponential backoff for 429/5xx errors.

    Returns the Response object on success.
    Raises requests.HTTPError after exhausting retries.
    """
    last_resp: requests.Response | None = None

    for attempt in range(max_retries + 1):
        try:
            resp = session.request(method, url, timeout=timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt >= max_retries:
                raise
            delay = (2 ** attempt) + random.uniform(0, 1)
            log.warning(
                "Network error on %s %s (attempt %d/%d): %s — retrying in %.1fs",
                method.upper(), url, attempt + 1, max_retries + 1, exc, delay,
            )
            time.sleep(delay)
            continue

        if resp.status_code < 400:
            return resp

        retryable = resp.status_code == 429 or resp.status_code >= 500
        if retryable and attempt < max_retries:
            # Respect Retry-After header if present
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = int(retry_after) + random.uniform(0, 1)
            else:
                delay = (2 ** attempt) + random.uniform(0, 1)
            log.warning(
                "HTTP %d on %s %s (attempt %d/%d) — retrying in %.1fs",
                resp.status_code, method.upper(), url, attempt + 1,
                max_retries + 1, delay,
            )
            time.sleep(delay)
            last_resp = resp
            continue

        # Non-retryable error or retries exhausted
        resp.raise_for_status()

    # Should not reach here, but just in case
    if last_resp is not None:
        last_resp.raise_for_status()
    raise RuntimeError("Retry loop exited unexpectedly")


def compress_image(path: Path, max_bytes: int = 950_000) -> Path:
    """Compress an image to fit within max_bytes (default 950 KB for Bluesky).

    Uses PIL/Pillow to progressively reduce JPEG quality.
    Returns the path to the (possibly new) compressed file.
    If the original is already small enough, returns it unchanged.

    Note: When a new compressed file is created, the caller is responsible
    for cleanup (e.g. ``compressed.unlink(missing_ok=True)`` after upload).
    """
    if path.stat().st_size <= max_bytes:
        return path

    from PIL import Image

    img = Image.open(path)
    if img.mode == "RGBA":
        img = img.convert("RGB")

    # Try progressively lower quality
    for quality in (85, 70, 55, 40, 30, 20):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= max_bytes:
            compressed = Path(tempfile.mktemp(suffix=".jpg"))
            compressed.write_bytes(buf.getvalue())
            log.info(
                "Compressed %s from %d to %d bytes (quality=%d)",
                path.name, path.stat().st_size, buf.tell(), quality,
            )
            return compressed

    # Last resort: resize
    scale = 0.75
    while scale > 0.2:
        new_size = (int(img.width * scale), int(img.height * scale))
        resized = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=40, optimize=True)
        if buf.tell() <= max_bytes:
            compressed = Path(tempfile.mktemp(suffix=".jpg"))
            compressed.write_bytes(buf.getvalue())
            log.info(
                "Compressed+resized %s to %dx%d (%d bytes)",
                path.name, new_size[0], new_size[1], buf.tell(),
            )
            return compressed
        scale -= 0.1

    raise ValueError(
        f"Could not compress {path} below {max_bytes} bytes even at minimum quality"
    )


def _bot_jitter(min_seconds: float = 0.5, max_seconds: float = 2.0) -> None:
    """Random sleep for bot-safety between consecutive API calls."""
    time.sleep(random.uniform(min_seconds, max_seconds))


# ── X (Twitter) Client ───────────────────────────────────────────────────


class XClient:
    """X (Twitter) API v2 client using OAuth1 via requests_oauthlib."""

    UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"

    def __init__(self, config: dict):
        """Initialize from social-config.json `platforms.x` section.

        Loads OAuth credentials from macOS Keychain using the service
        names specified in config["keychain"].
        """
        self.api_base = config.get("api_base", "https://api.x.com/2")
        self.max_chars = config.get("max_chars", 280)
        self.handle = config.get("handle", "")

        kc = config["keychain"]
        self.auth = OAuth1(
            keychain_get(kc["api_key"]),
            keychain_get(kc["api_secret"]),
            keychain_get(kc["access_token"]),
            keychain_get(kc["access_token_secret"]),
        )
        self.session = requests.Session()
        self.session.auth = self.auth

    def _upload_media(self, image_path: Path) -> str | None:
        """Upload media via v1.1 media/upload. Returns media_id_string or None."""
        try:
            with open(image_path, "rb") as f:
                resp = _api_call_with_retry(
                    self.session,
                    "POST",
                    self.UPLOAD_URL,
                    files={"media": f},
                    timeout=60,
                )
            data = resp.json()
            media_id = data.get("media_id_string")
            if media_id:
                log.info("Uploaded media to X: %s", media_id)
                return media_id
            log.error("X media upload returned no media_id: %s", data)
            return None
        except Exception as exc:
            log.error("X media upload failed: %s", exc)
            return None

    def post(self, content: str, image_path: Path | None = None) -> dict:
        """Post a tweet, optionally with an image.

        Returns {success, url, id, error}.
        """
        payload: dict[str, Any] = {"text": content}

        if image_path:
            media_id = self._upload_media(image_path)
            if media_id:
                payload["media"] = {"media_ids": [media_id]}

        try:
            resp = _api_call_with_retry(
                self.session,
                "POST",
                f"{self.api_base}/tweets",
                json=payload,
            )
            data = resp.json().get("data", {})
            tweet_id = data.get("id", "")
            url = f"https://x.com/{self.handle.lstrip('@')}/status/{tweet_id}" if tweet_id else ""
            return {"success": True, "url": url, "id": tweet_id}
        except requests.HTTPError as exc:
            error_body = ""
            if exc.response is not None:
                error_body = exc.response.text
            log.error("X post failed: %s — %s", exc, error_body)
            return {"success": False, "url": "", "id": "", "error": f"{exc}: {error_body}"}

    def reply(self, content: str, reply_to_id: str) -> dict:
        """Reply to a tweet by ID.

        Returns {success, url, id, error}.
        """
        payload: dict[str, Any] = {
            "text": content,
            "reply": {"in_reply_to_tweet_id": reply_to_id},
        }

        try:
            resp = _api_call_with_retry(
                self.session,
                "POST",
                f"{self.api_base}/tweets",
                json=payload,
            )
            data = resp.json().get("data", {})
            tweet_id = data.get("id", "")
            url = f"https://x.com/{self.handle.lstrip('@')}/status/{tweet_id}" if tweet_id else ""
            return {"success": True, "url": url, "id": tweet_id}
        except requests.HTTPError as exc:
            error_body = ""
            if exc.response is not None:
                error_body = exc.response.text
            log.error("X reply failed: %s — %s", exc, error_body)
            return {"success": False, "url": "", "id": "", "error": f"{exc}: {error_body}"}

    def follow(self, user_id: str) -> dict:
        """Follow a user by their X user ID.

        Returns {success, already_following, error}.
        """
        # We need our own user ID — get it from the authenticated user
        try:
            me_resp = _api_call_with_retry(
                self.session,
                "GET",
                f"{self.api_base}/users/me",
            )
            my_id = me_resp.json().get("data", {}).get("id")
            if not my_id:
                return {"success": False, "already_following": False, "error": "Could not determine authenticated user ID"}
        except requests.HTTPError as exc:
            return {"success": False, "already_following": False, "error": str(exc)}

        try:
            resp = _api_call_with_retry(
                self.session,
                "POST",
                f"{self.api_base}/users/{my_id}/following",
                json={"target_user_id": user_id},
            )
            data = resp.json().get("data", {})
            following = data.get("following", False)
            return {"success": True, "already_following": not following}
        except requests.HTTPError as exc:
            error_body = ""
            if exc.response is not None:
                error_body = exc.response.text
            # 403 can mean already following
            if exc.response is not None and exc.response.status_code == 403:
                return {"success": True, "already_following": True}
            log.error("X follow failed: %s — %s", exc, error_body)
            return {"success": False, "already_following": False, "error": f"{exc}: {error_body}"}

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Search recent tweets.

        Returns list of {id, text, author_id, author_name, created_at}.
        """
        params = {
            "query": query,
            "max_results": min(max(max_results, 10), 100),  # X API requires 10-100
            "tweet.fields": "created_at,author_id,text",
            "expansions": "author_id",
            "user.fields": "name,username",
        }

        try:
            resp = _api_call_with_retry(
                self.session,
                "GET",
                f"{self.api_base}/tweets/search/recent",
                params=params,
            )
            body = resp.json()
        except requests.HTTPError as exc:
            log.error("X search failed: %s", exc)
            return []

        # Build author lookup from includes
        users = {}
        for u in body.get("includes", {}).get("users", []):
            users[u["id"]] = {"name": u.get("name", ""), "username": u.get("username", "")}

        results = []
        for tweet in body.get("data", []):
            author_id = tweet.get("author_id", "")
            author_info = users.get(author_id, {})
            results.append({
                "id": tweet["id"],
                "text": tweet.get("text", ""),
                "author_id": author_id,
                "author_name": author_info.get("name", ""),
                "author_username": author_info.get("username", ""),
                "created_at": tweet.get("created_at", ""),
            })

        return results


# ── Bluesky Client ───────────────────────────────────────────────────────


class BlueskyClient:
    """Bluesky AT Protocol client with session caching."""

    def __init__(self, config: dict):
        """Initialize from social-config.json `platforms.bluesky` section.

        Loads app password from macOS Keychain.
        """
        self.api_base = config.get("api_base", "https://bsky.social/xrpc")
        self.handle = config["handle"]
        self.max_chars = config.get("max_chars", 300)

        kc = config["keychain"]
        self._app_password = keychain_get(kc["app_password"])

        self.session = requests.Session()
        self._jwt: str | None = None
        self._refresh_jwt: str | None = None
        self._did: str | None = None
        self._session_created_at: float = 0

    def _ensure_session(self) -> None:
        """Create or refresh xrpc session. Cache JWT for reuse.

        Sessions are refreshed if older than 30 minutes to avoid
        token expiry during long-running pipelines.
        """
        now = time.time()
        session_age = now - self._session_created_at

        # Try refresh if we have a refresh token and session is aging
        if self._refresh_jwt and session_age > 1800:
            try:
                resp = _api_call_with_retry(
                    self.session,
                    "POST",
                    f"{self.api_base}/com.atproto.server.refreshSession",
                    headers={"Authorization": f"Bearer {self._refresh_jwt}"},
                    max_retries=1,
                )
                data = resp.json()
                self._jwt = data["accessJwt"]
                self._refresh_jwt = data["refreshJwt"]
                self._did = data["did"]
                self._session_created_at = now
                self.session.headers["Authorization"] = f"Bearer {self._jwt}"
                log.info("Refreshed Bluesky session for %s", self.handle)
                return
            except Exception:
                log.info("Session refresh failed, creating new session")
                self._jwt = None

        # Create new session if needed
        if self._jwt and session_age < 1800:
            return

        resp = _api_call_with_retry(
            self.session,
            "POST",
            f"{self.api_base}/com.atproto.server.createSession",
            json={"identifier": self.handle, "password": self._app_password},
        )
        data = resp.json()
        self._jwt = data["accessJwt"]
        self._refresh_jwt = data["refreshJwt"]
        self._did = data["did"]
        self._session_created_at = now
        self.session.headers["Authorization"] = f"Bearer {self._jwt}"
        log.info("Created Bluesky session for %s (did=%s)", self.handle, self._did)

    @staticmethod
    def _parse_facets(text: str) -> list[dict]:
        """Extract URL and mention facets from post text.

        Returns AT Protocol richtext facets for links and @mentions.
        """
        facets = []

        # URLs
        url_pattern = re.compile(
            r'https?://[^\s\)\]\}>",]+',
            re.IGNORECASE,
        )
        for m in url_pattern.finditer(text):
            # Strip trailing punctuation that's likely not part of the URL
            url = m.group(0).rstrip(".,;:!?")
            byte_start = len(text[:m.start()].encode("utf-8"))
            byte_end = byte_start + len(url.encode("utf-8"))
            facets.append({
                "index": {"byteStart": byte_start, "byteEnd": byte_end},
                "features": [{
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": url,
                }],
            })

        # @mentions (basic — does not resolve DIDs here)
        mention_pattern = re.compile(r'(?<!\w)@([a-zA-Z0-9._-]+\.[a-zA-Z]+)')
        for m in mention_pattern.finditer(text):
            handle = m.group(1)
            byte_start = len(text[:m.start()].encode("utf-8"))
            byte_end = byte_start + len(m.group(0).encode("utf-8"))
            facets.append({
                "index": {"byteStart": byte_start, "byteEnd": byte_end},
                "features": [{
                    "$type": "app.bsky.richtext.facet#mention",
                    "did": handle,  # Caller should resolve to DID if needed
                }],
            })

        return facets

    def _upload_blob(self, image_path: Path) -> dict | None:
        """Upload an image blob. Compresses if over 950KB.

        Returns the blob reference dict or None on failure.
        """
        self._ensure_session()

        path = compress_image(image_path, max_bytes=950_000)

        mime = "image/jpeg"
        suffix = path.suffix.lower()
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".gif":
            mime = "image/gif"
        elif suffix == ".webp":
            mime = "image/webp"

        try:
            with open(path, "rb") as f:
                image_data = f.read()

            resp = _api_call_with_retry(
                self.session,
                "POST",
                f"{self.api_base}/com.atproto.repo.uploadBlob",
                headers={"Content-Type": mime},
                data=image_data,
                timeout=60,
            )
            blob = resp.json().get("blob")
            if blob:
                log.info("Uploaded blob to Bluesky: %d bytes", len(image_data))
                return blob
            log.error("Bluesky blob upload returned no blob ref")
            return None
        except Exception as exc:
            log.error("Bluesky blob upload failed: %s", exc)
            return None

    def post(self, content: str, image_path: Path | None = None) -> dict:
        """Post to Bluesky with optional image and auto-detected facets.

        Returns {success, url, uri, cid, error}.
        """
        self._ensure_session()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        record: dict[str, Any] = {
            "$type": "app.bsky.feed.post",
            "text": content,
            "createdAt": now,
        }

        # Add facets for URLs and mentions
        facets = self._parse_facets(content)
        if facets:
            record["facets"] = facets

        # Add image embed if provided
        if image_path:
            blob = self._upload_blob(image_path)
            if blob:
                record["embed"] = {
                    "$type": "app.bsky.embed.images",
                    "images": [{
                        "alt": "",
                        "image": blob,
                    }],
                }

        payload = {
            "repo": self._did,
            "collection": "app.bsky.feed.post",
            "record": record,
        }

        try:
            resp = _api_call_with_retry(
                self.session,
                "POST",
                f"{self.api_base}/com.atproto.repo.createRecord",
                json=payload,
            )
            data = resp.json()
            uri = data.get("uri", "")
            cid = data.get("cid", "")

            # Build web URL from AT URI:  at://did/app.bsky.feed.post/rkey
            web_url = ""
            if uri:
                parts = uri.split("/")
                if len(parts) >= 5:
                    rkey = parts[-1]
                    web_url = f"https://bsky.app/profile/{self.handle}/post/{rkey}"

            return {"success": True, "url": web_url, "uri": uri, "cid": cid}
        except requests.HTTPError as exc:
            error_body = ""
            if exc.response is not None:
                error_body = exc.response.text
            log.error("Bluesky post failed: %s — %s", exc, error_body)
            return {"success": False, "url": "", "uri": "", "cid": "", "error": f"{exc}: {error_body}"}

    def reply(
        self,
        content: str,
        parent_uri: str,
        parent_cid: str,
        root_uri: str | None = None,
        root_cid: str | None = None,
    ) -> dict:
        """Reply to a Bluesky post.

        If root_uri/root_cid are not provided, assumes parent IS the root
        (i.e., replying to a top-level post).

        Returns {success, url, uri, cid, error}.
        """
        self._ensure_session()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        record: dict[str, Any] = {
            "$type": "app.bsky.feed.post",
            "text": content,
            "createdAt": now,
            "reply": {
                "root": {
                    "uri": root_uri or parent_uri,
                    "cid": root_cid or parent_cid,
                },
                "parent": {
                    "uri": parent_uri,
                    "cid": parent_cid,
                },
            },
        }

        facets = self._parse_facets(content)
        if facets:
            record["facets"] = facets

        payload = {
            "repo": self._did,
            "collection": "app.bsky.feed.post",
            "record": record,
        }

        try:
            resp = _api_call_with_retry(
                self.session,
                "POST",
                f"{self.api_base}/com.atproto.repo.createRecord",
                json=payload,
            )
            data = resp.json()
            uri = data.get("uri", "")
            cid = data.get("cid", "")

            web_url = ""
            if uri:
                parts = uri.split("/")
                if len(parts) >= 5:
                    rkey = parts[-1]
                    web_url = f"https://bsky.app/profile/{self.handle}/post/{rkey}"

            return {"success": True, "url": web_url, "uri": uri, "cid": cid}
        except requests.HTTPError as exc:
            error_body = ""
            if exc.response is not None:
                error_body = exc.response.text
            log.error("Bluesky reply failed: %s — %s", exc, error_body)
            return {"success": False, "url": "", "uri": "", "cid": "", "error": f"{exc}: {error_body}"}

    def follow(self, did: str) -> dict:
        """Follow a user by DID.

        Returns {success, already_following, error}.
        """
        self._ensure_session()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        payload = {
            "repo": self._did,
            "collection": "app.bsky.graph.follow",
            "record": {
                "$type": "app.bsky.graph.follow",
                "subject": did,
                "createdAt": now,
            },
        }

        try:
            resp = _api_call_with_retry(
                self.session,
                "POST",
                f"{self.api_base}/com.atproto.repo.createRecord",
                json=payload,
            )
            resp.json()  # validate response
            return {"success": True, "already_following": False}
        except requests.HTTPError as exc:
            error_body = ""
            if exc.response is not None:
                error_body = exc.response.text
            # Duplicate follow record means already following
            if exc.response is not None and "duplicate" in error_body.lower():
                return {"success": True, "already_following": True}
            log.error("Bluesky follow failed: %s — %s", exc, error_body)
            return {"success": False, "already_following": False, "error": f"{exc}: {error_body}"}

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Search Bluesky posts.

        Returns list of dicts with post data including author follower counts
        and web URLs for engagement pipeline compatibility.
        """
        self._ensure_session()

        # Only search posts from the last 72 hours
        from datetime import datetime, timezone, timedelta
        since = (datetime.now(timezone.utc) - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "q": query,
            "limit": min(max_results, 100),
            "since": since,
            "sort": "latest",
        }

        try:
            resp = _api_call_with_retry(
                self.session,
                "GET",
                f"{self.api_base}/app.bsky.feed.searchPosts",
                params=params,
            )
            body = resp.json()
        except requests.HTTPError as exc:
            log.error("Bluesky search failed: %s", exc)
            return []

        results = []
        for post_view in body.get("posts", []):
            record = post_view.get("record", {})
            author = post_view.get("author", {})
            handle = author.get("handle", "")
            uri = post_view.get("uri", "")

            # Build web URL from AT URI
            web_url = ""
            if uri:
                parts = uri.split("/")
                if len(parts) >= 5:
                    rkey = parts[-1]
                    web_url = f"https://bsky.app/profile/{handle}/post/{rkey}"

            results.append({
                "uri": uri,
                "cid": post_view.get("cid", ""),
                "text": record.get("text", ""),
                "author_did": author.get("did", ""),
                "author_handle": handle,
                "author_name": author.get("displayName", ""),
                "followers_count": author.get("followersCount", 0),
                "following_count": author.get("followsCount", 0),
                "created_at": record.get("createdAt", ""),
                "like_count": post_view.get("likeCount", 0),
                "reply_count": post_view.get("replyCount", 0),
                "repost_count": post_view.get("repostCount", 0),
                "url": web_url,
                "platform": "bluesky",
            })

        return results

    def get_relationships(self, dids: list[str]) -> dict[str, dict]:
        """Check relationship status with a list of DIDs.

        Uses app.bsky.graph.getRelationships to check if we follow or
        are followed by each DID.

        Args:
            dids: List of DIDs to check (max 30 per call per API limits).

        Returns:
            Dict mapping DID to {following: bool, followed_by: bool}.
        """
        self._ensure_session()

        relationships = {}
        # Process in batches of 30 (API limit)
        for i in range(0, len(dids), 30):
            batch = dids[i:i + 30]
            params = {"actor": self._did, "others": batch}

            try:
                resp = _api_call_with_retry(
                    self.session,
                    "GET",
                    f"{self.api_base}/app.bsky.graph.getRelationships",
                    params=params,
                )
                body = resp.json()

                for rel in body.get("relationships", []):
                    did = rel.get("did", "")
                    if did:
                        relationships[did] = {
                            "following": bool(rel.get("following")),
                            "followed_by": bool(rel.get("followedBy")),
                        }
            except requests.HTTPError as exc:
                log.warning("Bluesky getRelationships failed: %s", exc)
                # Mark all as unknown (don't block engagement)
                for did in batch:
                    relationships[did] = {"following": False, "followed_by": False}

            if i + 30 < len(dids):
                _bot_jitter(0.3, 0.8)

        return relationships


# ── LinkedIn Client ──────────────────────────────────────────────────────


class LinkedInClient:
    """LinkedIn Community Management REST API client for posting text and image content.

    Uses the current Posts API (/rest/posts) and Images API (/rest/images),
    replacing the deprecated UGC Posts API (/v2/ugcPosts) and Assets API
    (/v2/assets).

    Requires:
        - OAuth2 access token with ``w_member_social`` scope.
        - ``Linkedin-Version`` header in YYYYMM format (set via config or
          defaults to ``202501``).

    See: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
    """

    # LinkedIn API version — YYYYMM format.  Update when migrating to a
    # newer version.  The version is sent on every request via the
    # ``Linkedin-Version`` header which is *required* by the REST API.
    DEFAULT_API_VERSION = "202501"

    def __init__(self, config: dict):
        """Initialize from social-config.json `platforms.linkedin` section.

        Loads access token from macOS Keychain.
        """
        # Base URL for the REST API — note: the new endpoints live under
        # /rest/ (e.g. /rest/posts) while userinfo remains at /v2/userinfo.
        self.api_base = config.get(
            "api_base", "https://api.linkedin.com"
        ).rstrip("/")
        # Strip a trailing /v2 if the config still has the old value so
        # callers don't need to update social-config.json immediately.
        if self.api_base.endswith("/v2"):
            self.api_base = self.api_base[: -len("/v2")]

        self.api_version = config.get("api_version", self.DEFAULT_API_VERSION)
        self.target_chars = config.get("target_chars", 1350)

        kc = config["keychain"]
        self._access_token = keychain_get(kc["access_token"])

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self._access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Linkedin-Version": self.api_version,
            "Content-Type": "application/json",
        })

        self._person_urn: str | None = None

    def _get_person_urn(self) -> str:
        """Get the authenticated user's LinkedIn person URN (cached).

        Calls the OpenID Connect userinfo endpoint (``/v2/userinfo``) which
        returns the ``sub`` claim as the member ID.
        """
        if self._person_urn:
            return self._person_urn

        resp = _api_call_with_retry(
            self.session,
            "GET",
            f"{self.api_base}/v2/userinfo",
        )
        data = resp.json()

        # The OIDC ``sub`` claim is the member identifier used to construct
        # the person URN (e.g. "782bbtaQ" -> "urn:li:person:782bbtaQ").
        member_id = data.get("sub", "")
        if not member_id:
            raise RuntimeError(
                f"Could not determine LinkedIn member ID from userinfo: {data}"
            )

        self._person_urn = f"urn:li:person:{member_id}"
        log.info("LinkedIn person URN: %s", self._person_urn)
        return self._person_urn

    def verify_token(self) -> dict:
        """Verify the access token works by calling /v2/userinfo.

        Returns the userinfo dict on success.
        Raises RuntimeError or requests.HTTPError on failure.
        """
        resp = _api_call_with_retry(
            self.session,
            "GET",
            f"{self.api_base}/v2/userinfo",
        )
        resp.raise_for_status()
        return resp.json()

    def _upload_image(self, image_path: Path) -> str | None:
        """Upload an image via the Images API (initializeUpload + binary PUT).

        Returns the image URN (``urn:li:image:…``) or None on failure.

        See: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/images-api
        """
        person_urn = self._get_person_urn()

        # Step 1: Initialize upload — returns an upload URL and image URN
        init_payload = {
            "initializeUploadRequest": {
                "owner": person_urn,
            }
        }

        try:
            resp = _api_call_with_retry(
                self.session,
                "POST",
                f"{self.api_base}/rest/images?action=initializeUpload",
                json=init_payload,
            )
            init_data = resp.json()

            upload_url = init_data["value"]["uploadUrl"]
            image_urn = init_data["value"]["image"]
        except Exception as exc:
            log.error("LinkedIn initializeUpload failed: %s", exc)
            return None

        # Step 2: Binary upload to the provided URL
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()

            _api_call_with_retry(
                self.session,
                "PUT",
                upload_url,
                headers={"Content-Type": "application/octet-stream"},
                data=image_data,
                timeout=60,
            )
            log.info("Uploaded image to LinkedIn: %s", image_urn)
            return image_urn
        except Exception as exc:
            log.error("LinkedIn image binary upload failed: %s", exc)
            return None

    def _upload_document(self, doc_path: Path) -> str | None:
        """Upload a document (PDF) via the Documents API (initializeUpload + binary PUT).

        Returns the document URN (``urn:li:document:…``) or None on failure.

        See: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/documents-api
        """
        person_urn = self._get_person_urn()

        init_payload = {
            "initializeUploadRequest": {
                "owner": person_urn,
            }
        }

        try:
            resp = _api_call_with_retry(
                self.session,
                "POST",
                f"{self.api_base}/rest/documents?action=initializeUpload",
                json=init_payload,
            )
            init_data = resp.json()

            upload_url = init_data["value"]["uploadUrl"]
            document_urn = init_data["value"]["document"]
        except Exception as exc:
            log.error("LinkedIn document initializeUpload failed: %s", exc)
            return None

        try:
            with open(doc_path, "rb") as f:
                doc_data = f.read()

            _api_call_with_retry(
                self.session,
                "PUT",
                upload_url,
                headers={"Content-Type": "application/octet-stream"},
                data=doc_data,
                timeout=60,
            )
            log.info("Uploaded document to LinkedIn: %s", document_urn)
            return document_urn
        except Exception as exc:
            log.error("LinkedIn document binary upload failed: %s", exc)
            return None

    def post(self, content: str, image_path: Path | None = None, document_path: Path | None = None) -> dict:
        """Post to LinkedIn via the Posts API (/rest/posts) with optional image or document.

        Returns {success, url, id, error}.
        """
        person_urn = self._get_person_urn()

        payload: dict[str, Any] = {
            "author": person_urn,
            "commentary": content,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        if document_path:
            document_urn = self._upload_document(document_path)
            if document_urn:
                payload["content"] = {
                    "media": {
                        "title": document_path.stem.replace("-", " ").replace("_", " ").title(),
                        "id": document_urn,
                    }
                }
        elif image_path:
            image_urn = self._upload_image(image_path)
            if image_urn:
                payload["content"] = {
                    "media": {
                        "id": image_urn,
                    }
                }

        try:
            resp = _api_call_with_retry(
                self.session,
                "POST",
                f"{self.api_base}/rest/posts",
                json=payload,
            )

            # LinkedIn returns the post ID in the x-restli-id header
            post_id = resp.headers.get("x-restli-id", "")
            if not post_id:
                post_id = resp.headers.get("X-RestLi-Id", "")
            if not post_id:
                data = resp.json() if resp.text else {}
                post_id = data.get("id", "")

            # Build URL: urn:li:share:12345 -> linkedin.com/feed/update/urn:li:share:12345
            url = ""
            if post_id:
                url = f"https://www.linkedin.com/feed/update/{post_id}"

            return {"success": True, "url": url, "id": post_id}
        except requests.HTTPError as exc:
            error_body = ""
            if exc.response is not None:
                error_body = exc.response.text
            log.error("LinkedIn post failed: %s — %s", exc, error_body)
            return {"success": False, "url": "", "id": "", "error": f"{exc}: {error_body}"}
