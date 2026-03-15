"""Tests for the social pipeline modules.

All external API calls and claude CLI calls are mocked.
No real HTTP requests are made.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from social.posting import (
    BlueskyClient,
    LinkedInClient,
    XClient,
    _api_call_with_retry,
    compress_image,
    keychain_get,
)

# ────────────────────────────────────────────────────────────────────────
# FIXTURES
# ────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


@pytest.fixture
def social_json():
    with open(PROJECT_ROOT / "policies" / "social.json") as f:
        return json.load(f)


@pytest.fixture
def mock_keychain():
    """Patch keychain_get so all platform clients can be instantiated."""
    with patch("social.posting.keychain_get", return_value="fake-secret") as m:
        yield m


@pytest.fixture
def x_config():
    return {
        "api_base": "https://api.x.com/2",
        "max_chars": 280,
        "handle": "@mindpattern_ai",
        "keychain": {
            "api_key": "x-api-key",
            "api_secret": "x-api-secret",
            "access_token": "x-access-token",
            "access_token_secret": "x-access-token-secret",
        },
    }


@pytest.fixture
def bluesky_config():
    return {
        "api_base": "https://bsky.social/xrpc",
        "handle": "webdevdad.bsky.social",
        "max_chars": 300,
        "keychain": {"app_password": "bluesky-app-password"},
    }


@pytest.fixture
def linkedin_config():
    return {
        "api_base": "https://api.linkedin.com/v2",
        "target_chars": 1350,
        "keychain": {"access_token": "linkedin-access-token"},
    }


# ────────────────────────────────────────────────────────────────────────
# social/posting.py — keychain_get
# ────────────────────────────────────────────────────────────────────────


class TestKeychainGet:
    """Tests for keychain_get()."""

    def test_missing_key_raises(self):
        """keychain_get raises RuntimeError when key is not found."""
        fake_result = subprocess.CompletedProcess(
            args=[], returncode=44, stdout="", stderr="not found"
        )
        with patch("social.posting.subprocess.run", return_value=fake_result):
            with pytest.raises(RuntimeError, match="Could not read"):
                keychain_get("nonexistent-key")

    def test_success_returns_stripped(self):
        """keychain_get returns stripped stdout on success."""
        fake_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="  my-secret-value  \n", stderr=""
        )
        with patch("social.posting.subprocess.run", return_value=fake_result):
            assert keychain_get("some-key") == "my-secret-value"


# ────────────────────────────────────────────────────────────────────────
# social/posting.py — compress_image
# ────────────────────────────────────────────────────────────────────────


class TestCompressImage:
    """Tests for compress_image()."""

    def test_small_image_returned_unchanged(self, tmp_path):
        """Image already under max_bytes is returned unchanged."""
        from PIL import Image

        img = Image.new("RGB", (10, 10), color="red")
        path = tmp_path / "small.jpg"
        img.save(path, format="JPEG")

        result = compress_image(path, max_bytes=999_999)
        assert result == path

    def test_large_image_gets_compressed(self, tmp_path):
        """Image over max_bytes gets compressed to a new smaller file."""
        from PIL import Image

        # Create a large-ish image
        img = Image.new("RGB", (500, 500), color="blue")
        path = tmp_path / "large.png"
        img.save(path, format="PNG")

        # Set max_bytes very low to force compression
        result = compress_image(path, max_bytes=500)
        assert result != path
        assert result.stat().st_size <= 500


# ────────────────────────────────────────────────────────────────────────
# social/posting.py — XClient.post
# ────────────────────────────────────────────────────────────────────────


class TestXClient:
    """Tests for XClient."""

    def test_post_makes_correct_request(self, mock_keychain, x_config):
        """XClient.post() sends a POST to /tweets with the text payload."""
        client = XClient(x_config)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"data": {"id": "123456"}}

        with patch.object(
            client.session, "request", return_value=mock_response
        ) as mock_req:
            result = client.post("Hello world")

        assert result["success"] is True
        assert "123456" in result["url"]
        assert result["id"] == "123456"

        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert call_args[0] == ("POST", "https://api.x.com/2/tweets")
        assert call_args[1]["json"] == {"text": "Hello world"}


# ────────────────────────────────────────────────────────────────────────
# social/posting.py — BlueskyClient
# ────────────────────────────────────────────────────────────────────────


class TestBlueskyClient:
    """Tests for BlueskyClient."""

    def test_ensure_session_caches_jwt(self, mock_keychain, bluesky_config):
        """_ensure_session() caches JWT so a second call does not re-auth."""
        client = BlueskyClient(bluesky_config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accessJwt": "jwt-token-abc",
            "refreshJwt": "refresh-abc",
            "did": "did:plc:test123",
        }

        with patch.object(
            client.session, "request", return_value=mock_response
        ) as mock_req:
            client._ensure_session()
            assert client._jwt == "jwt-token-abc"
            assert mock_req.call_count == 1

            # Second call within 30 minutes should NOT make a new request
            client._ensure_session()
            assert mock_req.call_count == 1

    def test_post_creates_facets_for_urls(self, mock_keychain, bluesky_config):
        """BlueskyClient.post() creates proper facets for URLs in content."""
        client = BlueskyClient(bluesky_config)
        # Pre-set session fields to skip _ensure_session network call
        client._jwt = "cached-jwt"
        client._did = "did:plc:test"
        client._session_created_at = time.time()
        client.session.headers["Authorization"] = "Bearer cached-jwt"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "uri": "at://did:plc:test/app.bsky.feed.post/abc123",
            "cid": "cid-xyz",
        }

        content = "Check this out https://mindpattern.ai for more"

        with patch.object(
            client.session, "request", return_value=mock_response
        ) as mock_req:
            result = client.post(content)

        assert result["success"] is True
        assert "abc123" in result["url"]

        # Verify the record sent contains facets
        call_args = mock_req.call_args
        payload = call_args[1]["json"]
        record = payload["record"]
        assert "facets" in record
        assert len(record["facets"]) >= 1
        facet = record["facets"][0]
        assert facet["features"][0]["$type"] == "app.bsky.richtext.facet#link"
        assert facet["features"][0]["uri"] == "https://mindpattern.ai"


# ────────────────────────────────────────────────────────────────────────
# social/posting.py — LinkedInClient
# ────────────────────────────────────────────────────────────────────────


class TestLinkedInClient:
    """Tests for LinkedInClient."""

    def test_post_uses_correct_api_flow(self, mock_keychain, linkedin_config):
        """LinkedInClient.post() gets person URN then posts to ugcPosts."""
        client = LinkedInClient(linkedin_config)

        userinfo_resp = MagicMock()
        userinfo_resp.status_code = 200
        userinfo_resp.json.return_value = {"sub": "member123"}

        post_resp = MagicMock()
        post_resp.status_code = 201
        post_resp.headers = {"X-RestLi-Id": "urn:li:share:99999"}
        post_resp.json.return_value = {}
        post_resp.text = ""

        call_count = [0]

        def side_effect(method, url, **kwargs):
            call_count[0] += 1
            if "userinfo" in url:
                return userinfo_resp
            return post_resp

        with patch.object(client.session, "request", side_effect=side_effect):
            result = client.post("Hello LinkedIn")

        assert result["success"] is True
        assert "urn:li:share:99999" in result["url"]
        assert call_count[0] == 2  # userinfo + ugcPosts


# ────────────────────────────────────────────────────────────────────────
# social/posting.py — _api_call_with_retry
# ────────────────────────────────────────────────────────────────────────


class TestApiCallWithRetry:
    """Tests for _api_call_with_retry()."""

    def test_retries_on_429(self):
        """Retries on HTTP 429 (rate limit) and eventually succeeds."""
        session = MagicMock(spec=requests.Session)

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {}

        resp_200 = MagicMock()
        resp_200.status_code = 200

        session.request.side_effect = [resp_429, resp_200]

        with patch("social.posting.time.sleep"):
            result = _api_call_with_retry(
                session, "GET", "https://example.com/api", max_retries=2
            )
        assert result.status_code == 200

    def test_retries_on_500(self):
        """Retries on HTTP 500 (server error) and eventually succeeds."""
        session = MagicMock(spec=requests.Session)

        resp_500 = MagicMock()
        resp_500.status_code = 500
        resp_500.headers = {}

        resp_200 = MagicMock()
        resp_200.status_code = 200

        session.request.side_effect = [resp_500, resp_200]

        with patch("social.posting.time.sleep"):
            result = _api_call_with_retry(
                session, "GET", "https://example.com/api", max_retries=2
            )
        assert result.status_code == 200

    def test_no_retry_on_400(self):
        """Does NOT retry on HTTP 400 -- raises immediately."""
        session = MagicMock(spec=requests.Session)

        resp_400 = MagicMock()
        resp_400.status_code = 400
        resp_400.raise_for_status.side_effect = requests.HTTPError(
            "400 Bad Request", response=resp_400
        )

        session.request.return_value = resp_400

        with pytest.raises(requests.HTTPError):
            _api_call_with_retry(
                session, "POST", "https://example.com/api", max_retries=3
            )

        # Should have been called only once (no retries)
        assert session.request.call_count == 1

    def test_no_retry_on_401(self):
        """Does NOT retry on HTTP 401 -- raises immediately."""
        session = MagicMock(spec=requests.Session)

        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.raise_for_status.side_effect = requests.HTTPError(
            "401 Unauthorized", response=resp_401
        )

        session.request.return_value = resp_401

        with pytest.raises(requests.HTTPError):
            _api_call_with_retry(
                session, "GET", "https://example.com/api", max_retries=3
            )

        assert session.request.call_count == 1


# ────────────────────────────────────────────────────────────────────────
# social/critics.py — deterministic_validate
# ────────────────────────────────────────────────────────────────────────


class TestDeterministicValidate:
    """Tests for deterministic_validate()."""

    def test_catches_over_length_x_post(self):
        """Posts >280 chars are flagged for X."""
        from social.critics import deterministic_validate

        long_post = "A" * 281 + " https://mindpattern.ai"
        errors = deterministic_validate("x", long_post)
        assert any("character limit" in e.lower() or "char" in e.lower() for e in errors)

    def test_catches_over_length_bluesky_post(self):
        """Posts >300 graphemes are flagged for Bluesky."""
        from social.critics import deterministic_validate

        long_post = "B" * 301
        errors = deterministic_validate("bluesky", long_post)
        assert any("grapheme" in e.lower() for e in errors)

    def test_catches_banned_words(self, social_json):
        """Banned words from social.json are caught."""
        from social.critics import deterministic_validate

        post = "This is a game-changer for AI https://mindpattern.ai"
        errors = deterministic_validate("x", post)
        assert any("game-changer" in e.lower() for e in errors)

    def test_catches_em_dash(self):
        """Em dash character is caught."""
        from social.critics import deterministic_validate

        post = "This is cool \u2014 really cool https://mindpattern.ai"
        errors = deterministic_validate("x", post)
        assert any("\u2014" in e for e in errors)

    def test_passes_valid_post(self):
        """A clean, short post with URL passes validation."""
        from social.critics import deterministic_validate

        post = "Interesting take on LLM evals. https://mindpattern.ai"
        errors = deterministic_validate("x", post)
        assert errors == []


# ────────────────────────────────────────────────────────────────────────
# social/critics.py — review_draft
# ────────────────────────────────────────────────────────────────────────


class TestReviewDraft:
    """Tests for review_draft()."""

    def test_returns_verdict_dict(self):
        """review_draft() returns a dict with verdict, feedback, scores."""
        mock_result = {
            "verdict": "APPROVED",
            "feedback": "Looks good",
            "scores": {
                "voice_authenticity": 8,
                "platform_fit": 9,
                "engagement_potential": 7,
            },
        }

        with patch("social.critics.run_agent_with_files", return_value=mock_result):
            from social.critics import review_draft

            result = review_draft("x", "Some test draft")

        assert result["verdict"] == "APPROVED"
        assert "feedback" in result
        assert "scores" in result

    def test_returns_revise_on_agent_failure(self):
        """review_draft() returns REVISE with zero scores when agent fails."""
        with patch("social.critics.run_agent_with_files", return_value=None):
            from social.critics import review_draft

            result = review_draft("x", "Some test draft")

        assert result["verdict"] == "REVISE"
        assert result["scores"]["voice_authenticity"] == 0
        assert result["scores"]["platform_fit"] == 0
        assert result["scores"]["engagement_potential"] == 0


# ────────────────────────────────────────────────────────────────────────
# social/critics.py — expedite
# ────────────────────────────────────────────────────────────────────────


class TestExpedite:
    """Tests for expedite()."""

    def test_returns_fail_on_agent_failure(self):
        """expedite() returns FAIL verdict (not auto-pass) when agent fails."""
        with patch("social.critics.run_agent_with_files", return_value=None):
            from social.critics import expedite

            result = expedite(
                drafts={"x": {"content": "test post"}},
                brief={"topic": "test"},
                images={},
            )

        assert result["verdict"] == "FAIL"
        assert "failed" in result["feedback"].lower() or "fail" in result["feedback"].lower()
        assert result["platform_verdicts"]["x"] == "FAIL"

    def test_returns_pass_with_platform_verdicts(self):
        """expedite() returns PASS with per-platform verdicts on success."""
        mock_result = {
            "verdict": "PASS",
            "feedback": "All drafts look good.",
            "platform_verdicts": {"x": "PASS", "linkedin": "PASS"},
            "scores": {
                "voice_match": 8,
                "framing_authenticity": 7,
                "platform_genre_fit": 9,
                "epistemic_calibration": 8,
                "structural_variation": 7,
                "rhetorical_framework": 8,
            },
        }

        with patch("social.critics.run_agent_with_files", return_value=mock_result):
            from social.critics import expedite

            result = expedite(
                drafts={
                    "x": {"content": "test x post"},
                    "linkedin": {"content": "test linkedin post"},
                },
                brief={"topic": "test"},
                images={},
            )

        assert result["verdict"] == "PASS"
        assert result["platform_verdicts"]["x"] == "PASS"
        assert result["platform_verdicts"]["linkedin"] == "PASS"
        assert result["scores"]["voice_match"] == 8
        # Legacy key preserved for pipeline compatibility
        assert "notes" in result

    def test_returns_fail_when_agent_returns_string(self):
        """expedite() returns FAIL when agent returns a raw string instead of dict."""
        # This reproduces the 'str' object has no attribute 'get' crash.
        # run_agent_with_files can return a str if json.loads parses a JSON
        # string literal (e.g. the agent wrote "PASS" instead of {"verdict":"PASS"}).
        with patch("social.critics.run_agent_with_files", return_value="PASS"):
            from social.critics import expedite

            result = expedite(
                drafts={"x": {"content": "test post"}},
                brief={"topic": "test"},
                images={},
            )

        assert result["verdict"] == "FAIL"
        assert result["platform_verdicts"]["x"] == "FAIL"

    def test_returns_pass_when_agent_returns_json_string(self):
        """expedite() parses JSON from a string result when possible."""
        json_str = json.dumps({
            "verdict": "PASS",
            "feedback": "Looks good.",
            "platform_verdicts": {"x": "PASS"},
            "scores": {"voice_match": 8, "framing_authenticity": 7,
                        "platform_genre_fit": 9, "epistemic_calibration": 8,
                        "structural_variation": 7, "rhetorical_framework": 8},
        })
        with patch("social.critics.run_agent_with_files", return_value=json_str):
            from social.critics import expedite

            result = expedite(
                drafts={"x": {"content": "test post"}},
                brief={"topic": "test"},
                images={},
            )

        assert result["verdict"] == "PASS"
        assert result["platform_verdicts"]["x"] == "PASS"


# ────────────────────────────────────────────────────────────────────────
# social/writers.py — _build_writer_prompt
# ────────────────────────────────────────────────────────────────────────


class TestBuildWriterAgentPrompt:
    """Tests for _build_writer_agent_prompt()."""

    def test_includes_brief_and_voice_guide(self):
        """Prompt includes the brief JSON and voice guide content."""
        from social.writers import _build_writer_agent_prompt

        with patch("social.writers._load_voice_guide", return_value="Be authentic."):
            prompt = _build_writer_agent_prompt(
                platform="x",
                brief={"anchor": "Test topic", "reaction": "Interesting."},
                iteration=1,
            )

        assert "Test topic" in prompt
        assert "Be authentic." in prompt
        assert "memory_cli.py get-exemplars --platform x" in prompt
        assert "memory_cli.py recent-corrections --platform x" in prompt

    def test_includes_feedback_on_iteration_gt_1(self):
        """When iteration > 1, prompt includes critic feedback section."""
        from social.writers import _build_writer_agent_prompt

        with patch("social.writers._load_voice_guide", return_value="Be real."):
            prompt = _build_writer_agent_prompt(
                platform="x",
                brief={"anchor": "Test"},
                iteration=2,
                feedback="The post was too long and used banned words.",
            )

        assert "Critic Feedback" in prompt
        assert "too long" in prompt
        assert "iteration 2" in prompt.lower()

    def test_includes_output_file_path(self):
        """Prompt tells agent where to write the draft file."""
        from social.writers import _build_writer_agent_prompt

        with patch("social.writers._load_voice_guide", return_value="Voice."):
            prompt = _build_writer_agent_prompt(
                platform="linkedin",
                brief={"anchor": "Test"},
                iteration=1,
            )

        assert "linkedin-draft.md" in prompt


# ────────────────────────────────────────────────────────────────────────
# social/writers.py — write_drafts
# ────────────────────────────────────────────────────────────────────────


class TestWriteDrafts:
    """Tests for write_drafts()."""

    def test_runs_platforms_in_parallel(self):
        """write_drafts() processes multiple platforms (mocked)."""
        mock_db = MagicMock()

        with patch("social.writers.run_agent_with_files", return_value={"text": "Draft text"}), \
             patch("social.writers.run_claude_prompt", return_value=("Draft text", 0)), \
             patch("social.writers._load_voice_guide", return_value="Voice guide."), \
             patch("memory.get_db", return_value=mock_db), \
             patch("memory.corrections.recent_corrections", return_value=[]), \
             patch("social.critics.run_agent_with_files", return_value={
                 "verdict": "APPROVED", "feedback": "", "scores": {},
             }), \
             patch("social.critics.PolicyEngine") as MockPolicy:

            mock_policy = MagicMock()
            mock_policy.validate_social_post.return_value = []
            MockPolicy.load_social.return_value = mock_policy

            from social.writers import write_drafts

            results = write_drafts(
                db=mock_db,
                brief={"anchor": "test", "reaction": "neat"},
                config={"social": {"max_iterations": 1}},
                platforms=["x", "linkedin"],
            )

        assert "x" in results
        assert "linkedin" in results
        for plat in ("x", "linkedin"):
            assert "content" in results[plat]


# ────────────────────────────────────────────────────────────────────────
# social/eic.py — select_topic
# ────────────────────────────────────────────────────────────────────────


class TestSelectTopic:
    """Tests for select_topic()."""

    def test_returns_none_on_kill_day(self):
        """select_topic returns None when EIC agent writes kill-day JSON."""
        kill_day_output = {
            "topics": [],
            "kill_explanation": "Nothing passed threshold today.",
        }

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        with patch("social.eic.run_agent_with_files", return_value=kill_day_output), \
             patch("social.eic._load_social_config", return_value={
                 "eic": {"quality_threshold": 5.0, "max_topics": 3},
                 "mindpattern_link": "https://mindpattern.ai",
             }), \
             patch("social.eic._get_recent_findings", return_value=[
                 {"id": 1, "run_date": "2026-03-14", "agent": "ai",
                  "title": "Test", "summary": "Test", "importance": "high",
                  "source_url": "https://example.com", "source_name": "Ex"},
             ]):

            from social.eic import select_topic

            result = select_topic(mock_db, "ramsay", "2026-03-14", max_retries=1)
            assert result is None

    def test_retries_on_duplicate_topic(self):
        """select_topic retries when topic is detected as duplicate."""
        topic_output = [{
            "rank": 1,
            "anchor": "Duplicate topic",
            "anchor_source": "example.com",
            "reaction": "Nice.",
            "confidence": "HIGH",
            "editorial_scores": {"composite": 8.0},
        }]

        mock_db = MagicMock()

        call_count = [0]

        def mock_run_agent(**kwargs):
            call_count[0] += 1
            return topic_output

        with patch("social.eic.run_agent_with_files", side_effect=mock_run_agent), \
             patch("social.eic._load_social_config", return_value={
                 "eic": {"quality_threshold": 5.0, "max_topics": 3},
                 "mindpattern_link": "https://mindpattern.ai",
             }), \
             patch("social.eic._get_recent_findings", return_value=[
                 {"id": 1, "run_date": "2026-03-14", "agent": "ai",
                  "title": "T", "summary": "S", "importance": "high",
                  "source_url": "https://x.com", "source_name": "X"},
             ]), \
             patch("memory.social.check_duplicate", return_value={
                 "is_duplicate": True,
                 "duplicates": [{"similarity": 0.92, "date": "2026-03-10"}],
             }):

            from social.eic import select_topic

            result = select_topic(mock_db, "ramsay", "2026-03-14", max_retries=3)

        # Should have retried 3 times and returned None (all were duplicates)
        assert call_count[0] == 3
        assert result is None


# ────────────────────────────────────────────────────────────────────────
# social/pipeline.py — SocialPipeline
# ────────────────────────────────────────────────────────────────────────


class TestSocialPipeline:
    """Tests for SocialPipeline."""

    def test_init_accepts_config_dict(self, mock_keychain):
        """SocialPipeline.__init__ accepts a config dict with platforms."""
        config = {
            "platforms": {
                "x": {
                    "enabled": True,
                    "handle": "@test",
                    "api_base": "https://api.x.com/2",
                    "max_chars": 280,
                    "keychain": {
                        "api_key": "k1",
                        "api_secret": "k2",
                        "access_token": "k3",
                        "access_token_secret": "k4",
                    },
                },
            },
            "imessage": {"phone": ""},
        }
        mock_db = MagicMock()

        with patch("social.pipeline.PolicyEngine") as MockPE, \
             patch("social.pipeline.ApprovalGateway"):
            MockPE.load_social.return_value = MagicMock()

            from social.pipeline import SocialPipeline

            pipeline = SocialPipeline(user_id="test", config=config, db=mock_db)

        assert pipeline.user_id == "test"
        assert pipeline.config is config
        assert "x" in pipeline._platform_clients

    def test_run_returns_kill_day_when_no_topic(self, mock_keychain):
        """Pipeline returns kill_day=True when select_topic returns None."""
        config = {
            "platforms": {
                "x": {
                    "enabled": True,
                    "handle": "@test",
                    "api_base": "https://api.x.com/2",
                    "max_chars": 280,
                    "keychain": {
                        "api_key": "k1",
                        "api_secret": "k2",
                        "access_token": "k3",
                        "access_token_secret": "k4",
                    },
                },
            },
            "imessage": {"phone": ""},
            "eic": {},
        }
        mock_db = MagicMock()

        with patch("social.pipeline.PolicyEngine") as MockPE, \
             patch("social.pipeline.ApprovalGateway"), \
             patch("social.pipeline.select_topic", return_value=None):
            MockPE.load_social.return_value = MagicMock()

            from social.pipeline import SocialPipeline

            pipeline = SocialPipeline(user_id="test", config=config, db=mock_db)
            result = pipeline.run()

        assert result["kill_day"] is True


# ────────────────────────────────────────────────────────────────────────
# social/approval.py — _imessage_send
# ────────────────────────────────────────────────────────────────────────


class TestImessageSend:
    """Tests for ApprovalGateway._imessage_send."""

    def test_constructs_correct_osascript_command(self):
        """_imessage_send builds the right osascript tell-block."""
        from social.approval import ApprovalGateway

        gateway = ApprovalGateway({"imessage": {"phone": "+15551234567"}})

        with patch("social.approval.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            gateway._imessage_send("+15551234567", "Test message")

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0][0] == "osascript"
        assert call_args[0][0][1] == "-e"
        script = call_args[0][0][2]
        assert "Messages" in script
        assert "+15551234567" in script
        assert "Test message" in script


# ────────────────────────────────────────────────────────────────────────
# social/engagement.py — EngagementPipeline
# ────────────────────────────────────────────────────────────────────────


class TestEngagementPipeline:
    """Tests for EngagementPipeline."""

    def test_init_accepts_config(self, mock_keychain):
        """EngagementPipeline.__init__ accepts config dict."""
        config = {
            "platforms": {
                "x": {
                    "enabled": True,
                    "handle": "@test",
                    "api_base": "https://api.x.com/2",
                    "max_chars": 280,
                    "keychain": {
                        "api_key": "k1",
                        "api_secret": "k2",
                        "access_token": "k3",
                        "access_token_secret": "k4",
                    },
                },
            },
            "imessage": {"phone": ""},
            "engagement": {"max_replies_per_day": 30},
        }
        mock_db = MagicMock()

        with patch("social.engagement.PolicyEngine") as MockPE, \
             patch("social.engagement.ApprovalGateway"):
            MockPE.load_social.return_value = MagicMock()

            from social.engagement import EngagementPipeline

            ep = EngagementPipeline(user_id="test", config=config, db=mock_db)

        assert ep.user_id == "test"
        assert ep.engagement_config["max_replies_per_day"] == 30

    def test_rate_limit_enforcement(self, mock_keychain):
        """Rate limits prevent over-posting when at the limit."""
        config = {
            "platforms": {
                "x": {
                    "enabled": True,
                    "handle": "@test",
                    "api_base": "https://api.x.com/2",
                    "max_chars": 280,
                    "keychain": {
                        "api_key": "k1",
                        "api_secret": "k2",
                        "access_token": "k3",
                        "access_token_secret": "k4",
                    },
                },
            },
            "imessage": {"phone": ""},
            "engagement": {"max_replies_per_day": 30},
        }
        mock_db = MagicMock()

        mock_policy = MagicMock()
        mock_policy.validate_rate_limits.return_value = {
            "allowed": False,
            "reason": "Post limit reached for x: 3/3 today",
            "current": 3,
            "limit": 3,
        }
        mock_policy.rules = {"posting": {"jitter_range_seconds": [1, 2]}}

        with patch("social.engagement.PolicyEngine") as MockPE, \
             patch("social.engagement.ApprovalGateway"), \
             patch("social.engagement.memory") as mock_memory:

            MockPE.load_social.return_value = mock_policy

            from social.engagement import EngagementPipeline

            ep = EngagementPipeline(user_id="test", config=config, db=mock_db)
            ep.policy = mock_policy

            candidates = [
                {
                    "platform": "x",
                    "author": "alice",
                    "author_id": "alice123",
                    "content": "Great post about AI",
                    "our_reply": "Good point.",
                },
            ]

            mock_memory.check_engagement.return_value = {
                "already_engaged": False,
                "count": 0,
            }

            with patch.object(ep, "_find_candidates", return_value=candidates), \
                 patch.object(ep, "_draft_replies", return_value=candidates):
                result = ep.run(dry_run=False)

        assert result["replies_posted"] == 0
        assert any("rate limit" in e.lower() for e in result["errors"])
