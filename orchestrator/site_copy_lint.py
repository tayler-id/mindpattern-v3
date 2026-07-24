"""Deterministic editorial lint for Rabbit Hole site copy.

This is not an AI detector. It is the shared, provider-neutral publishing
floor for public site story copy before the writer, critic, or artifact gate
can accept it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

COPY_FIELDS = ("title", "dek", "take", "why_now", "body_markdown")
PUBLIC_TEXT_FIELDS = ("title", "dek", "take", "why_now")
MAX_FIELD_CHARS = {
    "title": 90,
    "dek": 200,
    "take": 400,
    "why_now": 400,
    "body_markdown": 6000,
}

BANNED_WORDS = {
    "delve",
    "tapestry",
    "multifaceted",
    "testament",
    "realm",
    "landscape",
    "nuanced",
    "pivotal",
    "robust",
    "seamless",
    "comprehensive",
    "leverage",
    "utilize",
    "foster",
    "embark",
    "illuminate",
    "elucidate",
    "meticulous",
    "meticulously",
    "unwavering",
    "unprecedented",
    "transformative",
    "groundbreaking",
    "cutting-edge",
    "revolutionary",
    "innovative",
    "intricate",
    "profound",
    "vibrant",
    "whimsical",
    "quintessential",
    "enigma",
    "labyrinth",
    "gossamer",
    "virtuoso",
    "beacon",
    "crucible",
    "underscore",
    "spearheaded",
    "transcended",
    "reverberate",
    "symphony",
}

FAIL_PHRASE_PATTERNS = {
    "banned_phrase": [
        re.compile(r"\bin today's ever[- ]evolving (?:world|landscape)\b", re.I),
        re.compile(r"\bit'?s (?:important|worth) noting that\b", re.I),
        re.compile(r"\blet'?s delve into\b", re.I),
        re.compile(r"\bat the forefront of\b", re.I),
        re.compile(r"\ba testament to\b", re.I),
        re.compile(r"\bharness the power of\b", re.I),
        re.compile(r"\bas we navigate the complexities of\b", re.I),
        re.compile(r"\bnot just\b.+\bit'?s\b", re.I),
        re.compile(r"\bin (?:conclusion|summary|essence)\b", re.I),
        re.compile(r"\b(?:furthermore|moreover|additionally)\b", re.I),
    ],
}

INTERNAL_MACHINERY_PATTERNS = [
    re.compile(r"\b(?:evidence|graph) pack\b", re.I),
    re.compile(r"\b(?:the )?pipeline\b", re.I),
    re.compile(r"\bthese (?:instructions|rules)\b", re.I),
    re.compile(r"\bthis prompt\b", re.I),
    re.compile(r"\bas_of_date\b", re.I),
    re.compile(r"\bsite[- ]story (?:writer|critic)\b", re.I),
    re.compile(r"\b(?:AI|machine|model)[- ](?:written|generated)\b", re.I),
]

UNSUPPORTED_TEMPORAL_PATTERNS = [
    re.compile(r"\b(?:today|this week|this month|recently|currently)\b", re.I),
    # Bare "just" is usually quantitative ("just 86%") — only the temporal
    # "just <verb>" construction is an unsupported relative-time claim. The
    # unqualified word was rejecting ~90% of writer drafts (2026-07-07..13).
    re.compile(
        r"\bjust\s+(?:shipped|launched|released|announced|dropped|landed|"
        r"published|debuted|arrived|closed|raised|hit|crossed|passed|became|"
        r"got|went|added|introduced|unveiled|rolled)\b",
        re.I,
    ),
    re.compile(
        r"\bnow (?:ships?|shipped|launched|released|announced|adds?|offers?|made|"
        r"became|becomes|has|is|are)\b",
        re.I,
    ),
]

PROMOTIONAL_ADJECTIVES = {
    "amazing",
    "breakthrough",
    "dominant",
    "game-changing",
    "incredible",
    "major",
    "massive",
    "powerful",
    "remarkable",
    "significant",
    "stunning",
}
GENERIC_TAKE_PATTERNS = [
    re.compile(r"\bthis (?:matters|is important)\b", re.I),
    re.compile(r"\b(?:companies|teams|leaders|builders) (?:should|need to|must) pay attention\b", re.I),
    re.compile(r"\btime will tell\b", re.I),
    re.compile(r"\bit'?s (?:a|another) reminder\b", re.I),
]
VAGUE_ATTRIBUTION_RE = re.compile(
    r"\b(?:sources|reports|observers|analysts|experts|some people)\s+"
    r"(?:say|said|suggest|suggested|believe|think|expect|argue)\b",
    re.I,
)
SUMMARY_CLOSER_RE = re.compile(
    r"\b(?:in conclusion|in summary|to summarize|ultimately|at the end of the day|"
    r"exciting times ahead|only time will tell)\b",
    re.I,
)
CONTRACTION_RE = re.compile(
    r"\b\w+(?:n't|'re|'ve|'ll|'d|'m)\b|(?:can't|won't|don't|doesn't|isn't|aren't|"
    r"wasn't|weren't|it's|that's|there's|what's|who's|here's|we're|they're|you're)\b",
    re.I,
)
MARKDOWN_PUBLIC_RE = re.compile(r"\[[^\]]+\]\([^)]+\)|\*\*|__|`|^#{1,6}\s", re.M)
URL_RE = re.compile(r"https?://[^\s)\"']+")
WORD_RE = re.compile(r"\b[\w']+\b")


@dataclass(frozen=True)
class CopyLintIssue:
    code: str
    severity: str
    field: str
    excerpt: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def lint_site_copy(
    copy: dict[str, Any],
    *,
    allowed_urls: set[str] | None = None,
    required_fields: Iterable[str] = COPY_FIELDS,
    max_field_chars: dict[str, int] | None = None,
    include_revise: bool = True,
) -> list[CopyLintIssue]:
    """Return deterministic fail/revise issues for a story-copy payload."""
    issues: list[CopyLintIssue] = []
    required = tuple(required_fields)
    limits = max_field_chars or MAX_FIELD_CHARS

    if not isinstance(copy, dict):
        return [
            CopyLintIssue(
                "not_object",
                "fail",
                "*",
                _excerpt(str(type(copy))),
                "Copy payload must be a JSON object.",
            )
        ]

    for field in required:
        value = copy.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                CopyLintIssue(
                    "missing_field",
                    "fail",
                    field,
                    "",
                    f"{field} is required and must be a non-empty string.",
                )
            )
            continue
        limit = limits.get(field)
        if limit is not None and len(value.strip()) > limit:
            issues.append(
                CopyLintIssue(
                    "field_too_long",
                    "fail",
                    field,
                    _excerpt(value),
                    f"{field} is {len(value.strip())} chars; max is {limit}.",
                )
            )

    text_by_field = {
        field: str(copy.get(field) or "").strip()
        for field in COPY_FIELDS
        if isinstance(copy.get(field, ""), str)
    }
    joined = "\n".join(text_by_field.values())

    issues.extend(_hard_fail_voice_issues(text_by_field))
    issues.extend(_invented_url_issues(text_by_field, allowed_urls=allowed_urls or set()))
    issues.extend(_raw_markdown_issues(text_by_field))
    issues.extend(_internal_machinery_issues(text_by_field))
    issues.extend(_unsupported_temporal_issues(text_by_field))

    if include_revise:
        issues.extend(_revise_issues(copy, text_by_field, joined))

    return issues


def hard_fail_issues(issues: Iterable[CopyLintIssue]) -> list[CopyLintIssue]:
    return [issue for issue in issues if issue.severity == "fail"]


def revise_issues(issues: Iterable[CopyLintIssue]) -> list[CopyLintIssue]:
    return [issue for issue in issues if issue.severity == "revise"]


def first_voice_violation(text: str) -> str | None:
    """Compatibility helper for the previous writer voice gate."""
    if "\u2014" in text or "—" in text:
        return "em_dash"
    lowered = text.lower()
    for word in sorted(BANNED_WORDS):
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            return f"banned_word:{word}"
    return None


def format_lint_issues_for_prompt(issues: Iterable[CopyLintIssue]) -> str:
    """Stable JSON-ish block for critic/revision prompts."""
    payload = [issue.as_dict() for issue in issues]
    if not payload:
        return "[]"
    import json

    return json.dumps(payload, indent=2, sort_keys=True)


def copy_allowed_urls_from_refs(refs: Iterable[dict[str, Any]] | None) -> set[str]:
    return {
        str(ref.get("url", "")).rstrip(".,;")
        for ref in refs or []
        if isinstance(ref, dict) and ref.get("url")
    }


def _hard_fail_voice_issues(text_by_field: dict[str, str]) -> list[CopyLintIssue]:
    issues: list[CopyLintIssue] = []
    for field, text in text_by_field.items():
        if "\u2014" in text or "—" in text:
            issues.append(CopyLintIssue("em_dash", "fail", field, "—", "Em dashes are banned."))
        lowered = text.lower()
        for word in sorted(BANNED_WORDS):
            match = re.search(rf"\b{re.escape(word)}\b", lowered)
            if match:
                issues.append(
                    CopyLintIssue(
                        "banned_word",
                        "fail",
                        field,
                        _excerpt(text[match.start() : match.end()]),
                        f"Voice guide banned word: {word}.",
                    )
                )
                break
        for code, patterns in FAIL_PHRASE_PATTERNS.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    issues.append(
                        CopyLintIssue(
                            code,
                            "fail",
                            field,
                            _excerpt(match.group(0)),
                            "Hard-fail AI-copy phrase from the voice rules.",
                        )
                    )
                    break
    return issues


def _invented_url_issues(
    text_by_field: dict[str, str],
    *,
    allowed_urls: set[str],
) -> list[CopyLintIssue]:
    issues: list[CopyLintIssue] = []
    for field, text in text_by_field.items():
        for url in URL_RE.findall(text):
            normalized = url.rstrip(".,;")
            if normalized not in allowed_urls:
                issues.append(
                    CopyLintIssue(
                        "invented_url",
                        "fail",
                        field,
                        _excerpt(normalized),
                        "Copy cites a URL outside the provided source_refs.",
                    )
                )
    return issues


def _raw_markdown_issues(text_by_field: dict[str, str]) -> list[CopyLintIssue]:
    issues: list[CopyLintIssue] = []
    for field in PUBLIC_TEXT_FIELDS:
        text = text_by_field.get(field, "")
        match = MARKDOWN_PUBLIC_RE.search(text)
        if match:
            issues.append(
                CopyLintIssue(
                    "raw_markdown_public_field",
                    "fail",
                    field,
                    _excerpt(match.group(0)),
                    "Public summary fields must not contain raw markdown.",
                )
            )
    return issues


def _internal_machinery_issues(text_by_field: dict[str, str]) -> list[CopyLintIssue]:
    issues: list[CopyLintIssue] = []
    for field, text in text_by_field.items():
        for pattern in INTERNAL_MACHINERY_PATTERNS:
            match = pattern.search(text)
            if match:
                issues.append(
                    CopyLintIssue(
                        "internal_machinery",
                        "fail",
                        field,
                        _excerpt(match.group(0)),
                        "Public copy must not mention internal writing machinery.",
                    )
                )
                break
    return issues


def _unsupported_temporal_issues(text_by_field: dict[str, str]) -> list[CopyLintIssue]:
    issues: list[CopyLintIssue] = []
    for field, text in text_by_field.items():
        for pattern in UNSUPPORTED_TEMPORAL_PATTERNS:
            match = pattern.search(text)
            if match:
                issues.append(
                    CopyLintIssue(
                        "unsupported_temporal_claim",
                        "fail",
                        field,
                        _excerpt(match.group(0)),
                        "Use an absolute date or source-bound timing, not unsupported relative time.",
                    )
                )
                break
    return issues


def _revise_issues(
    copy: dict[str, Any],
    text_by_field: dict[str, str],
    joined: str,
) -> list[CopyLintIssue]:
    issues: list[CopyLintIssue] = []
    body = text_by_field.get("body_markdown", "")
    take = text_by_field.get("take", "")
    dek = text_by_field.get("dek", "")
    title = text_by_field.get("title", "")

    word_count = len(WORD_RE.findall(body))
    if body and not 150 <= word_count <= 350:
        issues.append(
            CopyLintIssue(
                "body_word_count",
                "revise",
                "body_markdown",
                _excerpt(body),
                f"Body is {word_count} words; target is 150-350.",
            )
        )

    for sentence in _sentences(body):
        sentence_words = len(WORD_RE.findall(sentence))
        if sentence_words > 25:
            issues.append(
                CopyLintIssue(
                    "overlong_sentence",
                    "revise",
                    "body_markdown",
                    _excerpt(sentence),
                    f"Sentence is {sentence_words} words; hard cap is 25.",
                )
            )
            break

    openers = _paragraph_openers(body)
    repeated = next((item for item in sorted(set(openers)) if openers.count(item) > 1), "")
    if repeated:
        issues.append(
            CopyLintIssue(
                "repeated_paragraph_opener",
                "revise",
                "body_markdown",
                repeated,
                "Multiple paragraphs open with the same word.",
            )
        )

    if take and any(pattern.search(take) for pattern in GENERIC_TAKE_PATTERNS):
        issues.append(
            CopyLintIssue(
                "generic_take",
                "revise",
                "take",
                _excerpt(take),
                "Take is generic advice instead of a falsifiable opinion.",
            )
        )

    if title and dek and _similarity(title, dek) >= 0.55:
        issues.append(
            CopyLintIssue(
                "echo_dek",
                "revise",
                "dek",
                _excerpt(dek),
                "Dek repeats the headline instead of advancing it.",
            )
        )

    if joined and not CONTRACTION_RE.search(joined):
        issues.append(
            CopyLintIssue(
                "missing_contraction",
                "revise",
                "*",
                "",
                "House voice requires at least one natural contraction.",
            )
        )

    promo_hits = _promotional_adjective_hits(joined)
    if len(promo_hits) >= 2:
        issues.append(
            CopyLintIssue(
                "promotional_adjective_pile",
                "revise",
                "*",
                ", ".join(promo_hits[:4]),
                "Promotional adjectives are carrying claims that need evidence.",
            )
        )

    match = VAGUE_ATTRIBUTION_RE.search(joined)
    if match:
        issues.append(
            CopyLintIssue(
                "vague_attribution",
                "revise",
                "*",
                _excerpt(match.group(0)),
                "Attribution must name the source, not vague observers.",
            )
        )

    last_paragraph = _last_paragraph(body)
    match = SUMMARY_CLOSER_RE.search(last_paragraph)
    if match:
        issues.append(
            CopyLintIssue(
                "summary_closer",
                "revise",
                "body_markdown",
                _excerpt(match.group(0)),
                "No summary or neat-bow closer.",
            )
        )

    sentence_lengths = [len(WORD_RE.findall(sentence)) for sentence in _sentences(body)]
    if len(sentence_lengths) >= 4 and max(sentence_lengths[:4]) - min(sentence_lengths[:4]) <= 3:
        issues.append(
            CopyLintIssue(
                "uniform_sentence_rhythm",
                "revise",
                "body_markdown",
                ", ".join(str(item) for item in sentence_lengths[:4]),
                "First four sentences have too-similar lengths.",
            )
        )

    return issues


def _sentences(text: str) -> list[str]:
    pieces = re.findall(r"[^.!?]+[.!?]", text.replace("\n", " "))
    return [re.sub(r"\s+", " ", piece).strip() for piece in pieces if piece.strip()]


def _paragraph_openers(text: str) -> list[str]:
    opener_stopwords = {"a", "an", "the", "this", "that", "it", "its"}
    openers: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        words = [word.lower() for word in WORD_RE.findall(paragraph)]
        opener = next((word for word in words if word not in opener_stopwords), "")
        if opener:
            openers.append(opener)
    return openers


def _last_paragraph(text: str) -> str:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    return paragraphs[-1] if paragraphs else ""


def _similarity(left: str, right: str) -> float:
    left_words = _content_words(left)
    right_words = _content_words(right)
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / max(1, min(len(left_words), len(right_words)))


def _content_words(text: str) -> set[str]:
    stop = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "for",
        "in",
        "is",
        "it",
        "of",
        "on",
        "the",
        "to",
        "with",
    }
    return {word.lower() for word in WORD_RE.findall(text) if len(word) > 2 and word.lower() not in stop}


def _promotional_adjective_hits(text: str) -> list[str]:
    lowered = text.lower()
    return [word for word in sorted(PROMOTIONAL_ADJECTIVES) if re.search(rf"\b{re.escape(word)}\b", lowered)]


def _excerpt(text: str, *, limit: int = 120) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]
