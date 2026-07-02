"""Junk entities/topics (Announced, Series, Top, ...) never reach the public site."""

from dashboard.routes.api import (
    _PUBLIC_ENTITY_SLUG_BLOCKLIST,
    _is_public_entity_ref,
    _public_story_edges,
    _public_story_entity_refs,
    _public_story_topic_terms,
)


def test_noise_names_are_rejected_as_entity_refs():
    for name in ["Announced", "Series", "Top", "Stories", "Source", "Today"]:
        assert not _is_public_entity_ref(slug=name.lower(), name=name), name
    assert _is_public_entity_ref(slug="vercel", name="Vercel")
    assert _is_public_entity_ref(slug="gpt-5", name="GPT-5")


def test_noise_slugs_are_blocklisted_for_entity_pages():
    for slug in ["announced", "series", "top", "stories", "source", "today"]:
        assert slug in _PUBLIC_ENTITY_SLUG_BLOCKLIST, slug
    assert "vercel" not in _PUBLIC_ENTITY_SLUG_BLOCKLIST


def test_entity_refs_filter_noise_but_keep_real_entities():
    refs = _public_story_entity_refs([
        {"slug": "announced", "name": "Announced"},
        {"slug": "vercel", "name": "Vercel"},
        {"slug": "the-latest", "name": "The Latest"},
    ])
    assert [ref["slug"] for ref in refs] == ["vercel"]


def test_topic_terms_filter_noise():
    terms = _public_story_topic_terms(
        ["announced", "being", "easy", "hydrogen", "commerce", "Top", "today"]
    )
    assert "announced" not in terms
    assert "today" not in terms
    assert {"hydrogen", "commerce"} <= set(terms)


def test_story_edges_drop_noise_entities_and_topics():
    edges = _public_story_edges([
        {"kind": "entity", "relationship": "mentions_entity", "id": "announced",
         "label": "Announced", "target_url": "/e/announced"},
        {"kind": "entity", "relationship": "mentions_entity", "id": "vercel",
         "label": "Vercel", "target_url": "/e/vercel"},
        {"kind": "topic", "relationship": "mentions_topic", "id": "being",
         "label": "being", "target_url": ""},
        {"kind": "topic", "relationship": "mentions_topic", "id": "hydrogen",
         "label": "hydrogen", "target_url": ""},
        {"kind": "source_domain", "relationship": "cites_source_domain", "id": "vercel.com",
         "label": "vercel.com", "target_url": "/source/vercel.com"},
    ])
    ids = [edge["id"] for edge in edges]
    assert "announced" not in ids
    assert "being" not in ids
    assert {"vercel", "hydrogen", "vercel.com"} <= set(ids)


def test_known_acronym_entities_are_allowed_as_slugs():
    from dashboard.routes.api import _is_public_entity_slug

    for slug in ["mcp", "gpt", "cve"]:
        assert _is_public_entity_slug(slug), slug
    for slug in ["and", "the", "top", "ai", "x"]:
        assert not _is_public_entity_slug(slug), slug
    assert _is_public_entity_slug("vercel")
