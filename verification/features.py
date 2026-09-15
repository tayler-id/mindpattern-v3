"""Stable feature registry and behavior assertions."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from verification.models import AssertionResult, Feature, RequestResult

SKILL_DOC = ".agents/skills/verify-mindpattern/SKILL.md"

FEATURES = (
    Feature(
        id="stories",
        description="Published story listing and detail visibility",
        routes=("/api/stories", "/api/stories/{slug}"),
        verifier="verify_stories",
        limits=(
            "Uses one synthetic publishable story, one draft, and one invalid story.",
            "Does not exercise production report history or structured issue fallback.",
        ),
    ),
    Feature(
        id="story-search",
        description="Story-only public search filtering",
        routes=("/api/search/site",),
        verifier="verify_story_search",
        limits=(
            "Restricts types to stories and does not load embedding models.",
            "Covers literal term matching against the synthetic story corpus.",
        ),
    ),
    Feature(
        id="site-artifacts",
        description="Public run and corpus artifact safety",
        routes=("/api/site/runs/{date}", "/api/site/corpus/{date}"),
        verifier="verify_site_artifacts",
        limits=(
            "Uses fixed synthetic artifacts for 2026-07-01.",
            "Checks response redaction, missing dates, and invalid dates only.",
        ),
    ),
    Feature(
        id="sitemap",
        description="Public sitemap story inventory",
        routes=("/api/site/sitemap",),
        verifier="verify_sitemap",
        limits=(
            "The fixture has no entity dossiers, source dossiers, or briefings.",
            "Checks that only the publishable synthetic story is advertised.",
        ),
    ),
    Feature(
        id="private-access",
        description="Default-deny access to the private user registry",
        routes=("/api/users",),
        verifier="verify_private_access",
        limits=(
            "Uses an ephemeral generated bearer token and synthetic users.json.",
            "Does not exercise pipeline-secret or browser query-token authentication.",
        ),
    ),
)

FEATURE_BY_ID = {feature.id: feature for feature in FEATURES}

Fetch = Callable[[str, dict[str, str] | None], Awaitable[RequestResult]]


def feature_payload(feature: Feature) -> dict[str, Any]:
    payload = feature.to_dict()
    payload["skill_doc"] = SKILL_DOC
    payload["feature_doc"] = f".agents/skills/verify-mindpattern/references/features/{feature.id}.md"
    return payload


def _assert(name: str, expected: Any, observed: Any) -> AssertionResult:
    return AssertionResult(name=name, passed=observed == expected, expected=expected, observed=observed)


def _contains_no_sensitive_markers(body: Any) -> bool:
    serialized = json.dumps(body, sort_keys=True)
    return not any(
        marker in serialized
        for marker in (
            "owner@verification.invalid",
            "fixture-token-must-not-leak",
            "raw_slack_body",
            "reader@verification.invalid",
            "subscriber_email",
        )
    )


async def verify_stories(fetch: Fetch) -> tuple[list[RequestResult], list[AssertionResult]]:
    listing = await fetch("/api/stories?user=ramsay&limit=10", None)
    detail = await fetch("/api/stories/verification-story?user=ramsay", None)
    draft = await fetch("/api/stories/verification-draft?user=ramsay", None)
    invalid = await fetch("/api/stories/verification-invalid?user=ramsay", None)
    missing = await fetch("/api/stories/absent-story?user=ramsay", None)
    items = listing.body.get("items", []) if isinstance(listing.body, dict) else []
    story = detail.body if isinstance(detail.body, dict) else {}
    assertions = [
        _assert("story listing status", 200, listing.status),
        _assert("published story listing", ["verification-story"], [item.get("slug") for item in items]),
        _assert("published story count", 1, listing.body.get("total") if isinstance(listing.body, dict) else None),
        _assert("story detail status", 200, detail.status),
        _assert("story detail slug", "verification-story", story.get("slug")),
        _assert("story source URL", ["https://example.test/verification-story"], [
            source.get("url") for source in story.get("source_refs", [])
        ]),
        _assert("story content", "Verification confirms the published story contract.", story.get("body_markdown")),
        _assert("story provenance redaction", "passed", (story.get("provenance") or {}).get("redaction_status")),
        _assert("draft story is hidden", 404, draft.status),
        _assert("invalid story is hidden", 404, invalid.status),
        _assert("missing story is unavailable", 404, missing.status),
    ]
    return [listing, detail, draft, invalid, missing], assertions


async def verify_story_search(fetch: Fetch) -> tuple[list[RequestResult], list[AssertionResult]]:
    match = await fetch("/api/search/site?q=verification&types=stories&user=ramsay", None)
    no_match = await fetch("/api/search/site?q=absent-term&types=stories&user=ramsay", None)
    draft = await fetch("/api/search/site?q=draft&types=stories&user=ramsay", None)

    def slugs(result: RequestResult) -> list[str]:
        if not isinstance(result.body, dict):
            return []
        return [item.get("slug") for item in result.body.get("groups", {}).get("stories", [])]

    assertions = [
        _assert("story search status", 200, match.status),
        _assert("no-match search status", 200, no_match.status),
        _assert("draft search status", 200, draft.status),
        *[_assert("search response kind", "site_search", result.body.get("kind") if isinstance(result.body, dict) else None)
          for result in (match, no_match, draft)],
        _assert("matching story", ["verification-story"], slugs(match)),
        _assert("no-match result", [], slugs(no_match)),
        _assert("draft omitted from search", [], slugs(draft)),
    ]
    return [match, no_match, draft], assertions


async def verify_site_artifacts(fetch: Fetch) -> tuple[list[RequestResult], list[AssertionResult]]:
    run = await fetch("/api/site/runs/2026-07-01?user=ramsay", None)
    corpus = await fetch("/api/site/corpus/2026-07-01?user=ramsay", None)
    missing = await fetch("/api/site/runs/2026-07-02?user=ramsay", None)
    invalid = await fetch("/api/site/runs/2026-99-99?user=ramsay", None)
    run_body = run.body if isinstance(run.body, dict) else {}
    corpus_body = corpus.body if isinstance(corpus.body, dict) else {}
    assertions = [
        _assert("run artifact status", 200, run.status),
        _assert("run story count", 1, run_body.get("generated_story_count")),
        _assert("run redaction", True, _contains_no_sensitive_markers(run.body)),
        _assert("corpus artifact status", 200, corpus.status),
        _assert("corpus entity count", 14000, (corpus_body.get("counts") or {}).get("entities")),
        _assert("corpus redaction", True, _contains_no_sensitive_markers(corpus.body)),
        _assert("missing artifact response", {"status": 200, "body_status": "missing"}, {
            "status": missing.status,
            "body_status": missing.body.get("status") if isinstance(missing.body, dict) else None,
        }),
        _assert("invalid date rejected", 404, invalid.status),
    ]
    return [run, corpus, missing, invalid], assertions


async def verify_sitemap(fetch: Fetch) -> tuple[list[RequestResult], list[AssertionResult]]:
    sitemap = await fetch("/api/site/sitemap?user=ramsay", None)
    body = sitemap.body if isinstance(sitemap.body, dict) else {}
    slugs = [item.get("slug") for item in body.get("stories", [])]
    assertions = [
        _assert("sitemap status", 200, sitemap.status),
        _assert("sitemap kind", "site_sitemap", body.get("kind")),
        _assert("public stories only", ["verification-story"], slugs),
    ]
    return [sitemap], assertions


async def verify_private_access(fetch: Fetch) -> tuple[list[RequestResult], list[AssertionResult]]:
    anonymous = await fetch("/api/users", None)
    invalid = await fetch("/api/users", {"authorization": "Bearer invalid-verification-token"})
    authenticated = await fetch("/api/users", {"authorization": "Bearer __generated__"})
    body = authenticated.body if isinstance(authenticated.body, dict) else {}
    users = body.get("users", [])
    assertions = [
        _assert("anonymous private access denied", 401, anonymous.status),
        _assert("invalid bearer denied", 401, invalid.status),
        _assert("generated bearer accepted", 200, authenticated.status),
        _assert("synthetic user returned", ["ramsay"], [user.get("id") for user in users]),
        _assert("synthetic identity only", ["fixture-user@verification.invalid"], [user.get("email") for user in users]),
    ]
    return [anonymous, invalid, authenticated], assertions


VERIFIERS = {
    "verify_stories": verify_stories,
    "verify_story_search": verify_story_search,
    "verify_site_artifacts": verify_site_artifacts,
    "verify_sitemap": verify_sitemap,
    "verify_private_access": verify_private_access,
}
