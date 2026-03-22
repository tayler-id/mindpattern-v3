"""Post-synthesis newsletter quality evaluation.

All checks are deterministic Python — no LLM calls needed.
Scores a newsletter on 6 dimensions plus an overall composite.
"""

import re
from collections import Counter


class NewsletterEvaluator:
    """Score a newsletter on coverage, dedup, sources, actionability, length, and topic balance."""

    def __init__(self, db):
        """Takes memory module db connection for similarity search.

        Args:
            db: sqlite3.Connection to the memory database (memory.db).
        """
        self.db = db

    def evaluate(
        self,
        newsletter_text: str,
        agent_reports: list[dict],
        user_preferences: list[dict],
    ) -> dict:
        """Score newsletter on 6 dimensions.

        Args:
            newsletter_text: The full newsletter markdown text.
            agent_reports: List of dicts with at least 'agent', 'title', 'importance' keys
                           from each agent's findings.
            user_preferences: List of dicts with 'topic' and 'weight' keys from
                              user_preferences table.

        Returns:
            Dict with keys: coverage, dedup, sources, actionability, length,
            topic_balance, overall (all floats 0.0-1.0).
        """
        coverage = self._check_coverage(newsletter_text, agent_reports)
        dedup = self._check_dedup(newsletter_text)
        sources = self._check_sources(newsletter_text)
        actionability = self._check_actionability(newsletter_text)
        length = self._check_length(newsletter_text)
        topic_balance = self._check_balance(newsletter_text, user_preferences)

        # Weighted composite: coverage and dedup matter most
        overall = (
            coverage * 0.25
            + dedup * 0.20
            + sources * 0.15
            + actionability * 0.15
            + length * 0.10
            + topic_balance * 0.15
        )

        # Defense in depth: clamp overall to [0.0, 1.0]
        overall = min(max(overall, 0.0), 1.0)

        return {
            "coverage": round(coverage, 3),
            "dedup": round(dedup, 3),
            "sources": round(sources, 3),
            "actionability": round(actionability, 3),
            "length": round(length, 3),
            "topic_balance": round(topic_balance, 3),
            "overall": round(overall, 3),
        }

    def _check_coverage(self, newsletter: str, reports: list[dict]) -> float:
        """Are high-importance stories from agent reports represented?

        Checks whether titles/keywords from high-importance findings appear
        in the newsletter text. Score 0.0-1.0.
        """
        if not reports:
            return 1.0  # Nothing to cover

        # Filter to high and critical importance findings
        high_reports = [
            r for r in reports
            if r.get("importance", "medium") in ("high", "critical")
        ]

        if not high_reports:
            # No high-importance findings — check medium ones instead
            high_reports = [
                r for r in reports
                if r.get("importance", "medium") == "medium"
            ]

        if not high_reports:
            return 1.0

        newsletter_lower = newsletter.lower()
        covered = 0

        for report in high_reports:
            title = report.get("title", "")
            if not title:
                continue

            # Check if significant words from the title appear in the newsletter
            # (strip common words for more meaningful matching)
            words = _extract_significant_words(title)
            if not words:
                covered += 1
                continue

            # Require at least 50% of significant words to match
            matches = sum(1 for w in words if w in newsletter_lower)
            if matches >= max(1, len(words) * 0.5):
                covered += 1

        return covered / len(high_reports)

    def _check_dedup(self, newsletter: str) -> float:
        """Is any story repeated across sections? Score 0.0-1.0 (1.0 = no dupes).

        Extracts section headings and their content, then checks for significant
        overlap between sections using keyword intersection.
        """
        sections = _split_into_sections(newsletter)

        if len(sections) <= 1:
            return 1.0

        # Extract significant words per section
        section_words = []
        for _heading, body in sections:
            words = set(_extract_significant_words(body))
            if len(words) >= 3:  # Only consider sections with enough content
                section_words.append(words)

        if len(section_words) <= 1:
            return 1.0

        # Check pairwise overlap
        duplicate_pairs = 0
        total_pairs = 0

        for i in range(len(section_words)):
            for j in range(i + 1, len(section_words)):
                total_pairs += 1
                intersection = section_words[i] & section_words[j]
                smaller = min(len(section_words[i]), len(section_words[j]))
                if smaller > 0:
                    overlap = len(intersection) / smaller
                    if overlap > 0.6:  # >60% overlap = duplicate
                        duplicate_pairs += 1

        if total_pairs == 0:
            return 1.0

        return 1.0 - (duplicate_pairs / total_pairs)

    def _check_sources(self, newsletter: str) -> float:
        """Does every section have source URLs?

        Score = sections_with_urls / total_sections.
        """
        sections = _split_into_sections(newsletter)

        if not sections:
            return 0.0

        url_pattern = re.compile(r'https?://[^\s\)\]>]+')
        sections_with_urls = 0

        for _heading, body in sections:
            if url_pattern.search(body):
                sections_with_urls += 1

        return sections_with_urls / len(sections)

    def _check_actionability(self, newsletter: str) -> float:
        """Does the newsletter have actionable takeaways?

        Checks for presence of:
        - "Why it matters" or "Why this matters" sections/phrases (0.3)
        - "Try this", "Action items", "What to do" sections (0.3)
        - Skills section or practical tips (0.2)
        - Bullet points with actionable language (0.2)
        """
        text_lower = newsletter.lower()
        score = 0.0

        # Check for "why it matters" patterns
        why_patterns = ["why it matters", "why this matters", "what it means", "significance"]
        if any(p in text_lower for p in why_patterns):
            score += 0.3

        # Check for action-oriented sections
        action_patterns = [
            "try this", "action items", "what to do", "next steps",
            "how to", "get started", "takeaway", "takeaways",
            "practical", "apply this",
        ]
        if any(p in text_lower for p in action_patterns):
            score += 0.3

        # Check for skills section
        skill_patterns = ["## skills", "## skill", "skills to learn", "skill of the day"]
        if any(p in text_lower for p in skill_patterns):
            score += 0.2

        # Check for actionable bullet points (lines starting with - or * followed by a verb)
        action_verbs = [
            "use ", "try ", "build ", "create ", "implement ", "test ",
            "read ", "check ", "learn ", "start ", "stop ", "consider ",
            "explore ", "review ", "watch ", "install ", "set up ",
        ]
        lines = newsletter.lower().split("\n")
        actionable_bullets = 0
        total_bullets = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("- ", "* ", "1.", "2.", "3.")):
                total_bullets += 1
                content = stripped.lstrip("-*0123456789. ")
                if any(content.startswith(v) for v in action_verbs):
                    actionable_bullets += 1

        if total_bullets > 0 and actionable_bullets / total_bullets > 0.1:
            score += 0.2

        return min(score, 1.0)

    def _check_length(self, newsletter: str) -> float:
        """Is the newsletter 3000-5000 words? 1.0 if in range, scaled down outside.

        Returns:
            1.0 if word count is in [3000, 5000]
            Linearly scaled toward 0.0 outside that range
            Minimum 0.1 to avoid zeroing out the score entirely
        """
        word_count = len(newsletter.split())

        if 3000 <= word_count <= 5000:
            return 1.0

        if word_count < 3000:
            # Scale from 0.1 at 0 words to 1.0 at 3000 words
            return max(0.1, word_count / 3000)

        # word_count > 5000: scale down, reaching 0.5 at 8000 words
        overage = word_count - 5000
        return max(0.1, 1.0 - (overage / 6000))

    def _check_balance(self, newsletter: str, preferences: list[dict]) -> float:
        """Does coverage match user preferences? Score 0.0-1.0.

        Checks whether topics the user cares about (by weight) appear in the
        newsletter proportionally. Higher-weighted topics should have more coverage.

        Negative-weight preferences mean "avoid this topic" and are excluded
        from the balance calculation (they don't contribute to coverage goals).
        Duplicate preference names are deduped, keeping the highest absolute weight.
        """
        if not preferences:
            return 1.0  # No preferences to match

        # Dedup preferences by topic name, keeping the highest absolute weight
        seen: dict[str, dict] = {}
        for pref in preferences:
            topic = pref.get("topic", "").lower().strip()
            if not topic:
                continue
            weight = pref.get("weight", 1.0)
            if topic not in seen or abs(weight) > abs(seen[topic].get("weight", 1.0)):
                seen[topic] = pref

        deduped = list(seen.values())

        # Filter out negative-weight preferences — they mean "avoid this topic"
        # and should not factor into balance scoring
        positive_prefs = [p for p in deduped if p.get("weight", 1.0) > 0]

        if not positive_prefs:
            return 1.0  # No positive preferences to match

        newsletter_lower = newsletter.lower()

        # Calculate expected vs actual coverage using only positive-weight prefs
        total_weight = sum(p.get("weight", 1.0) for p in positive_prefs)
        if total_weight == 0:
            return 1.0

        covered_weight = 0.0
        for pref in positive_prefs:
            topic = pref.get("topic", "").lower()
            weight = pref.get("weight", 1.0)

            if not topic:
                continue

            # Check if topic words appear in the newsletter
            topic_words = _extract_significant_words(topic)
            if not topic_words:
                covered_weight += weight
                continue

            matches = sum(1 for w in topic_words if w in newsletter_lower)
            if matches >= max(1, len(topic_words) * 0.4):
                covered_weight += weight

        # Defense in depth: clamp to [0.0, 1.0]
        return min(covered_weight / total_weight, 1.0)


# ── Private helpers ──────────────────────────────────────────────────────


# Common English stop words to skip during keyword extraction
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "its", "was", "are", "be",
    "has", "had", "have", "this", "that", "these", "those", "will", "can",
    "do", "does", "did", "not", "no", "so", "if", "as", "up", "out",
    "about", "into", "over", "after", "new", "also", "more", "how", "what",
    "when", "where", "who", "why", "all", "each", "every", "both",
})


def _extract_significant_words(text: str) -> list[str]:
    """Extract meaningful words from text (lowercase, no stop words, 3+ chars)."""
    words = re.findall(r'[a-z0-9]+', text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) >= 3]


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown text into (heading, body) tuples by ## headings.

    Returns a list of (heading_text, section_body) pairs.
    Top-level content before any heading is included as ("", body).
    """
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        if line.startswith("## ") or line.startswith("# "):
            # Save previous section
            if current_body:
                body = "\n".join(current_body).strip()
                if body:
                    sections.append((current_heading, body))
            current_heading = line.lstrip("#").strip()
            current_body = []
        else:
            current_body.append(line)

    # Save final section
    if current_body:
        body = "\n".join(current_body).strip()
        if body:
            sections.append((current_heading, body))

    return sections


if __name__ == "__main__":
    import sqlite3

    # Create in-memory DB for testing
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row

    evaluator = NewsletterEvaluator(db)

    # Build a sample newsletter
    sample = """# Daily Research — 2026-03-14

## AI Model Updates

OpenAI released GPT-5 with improved reasoning capabilities. The model shows
significant improvements in code generation and mathematical reasoning.

**Why it matters:** This represents a major leap in AI capability that will
affect developer tooling across the industry.

Source: https://openai.com/blog/gpt5

## Developer Tools

GitHub Copilot now supports multi-file editing with context-aware suggestions.
The new agent mode can refactor entire codebases.

Try this: Install the latest VS Code extension and enable agent mode in settings.

Source: https://github.blog/copilot-agent

## Skills to Learn

- Use the new Claude Code CLI for automated code review
- Try parallel agent execution for research tasks
- Build a simple RAG pipeline with local embeddings
- Learn about vector databases for semantic search
- Consider implementing feedback loops in your AI workflows
- Explore multi-agent architectures for complex tasks

## Emerging Patterns

Autonomous AI agents are becoming more prevalent in production systems.
Multi-agent architectures are showing promise for complex research tasks.

Source: https://arxiv.org/example
"""

    agent_reports = [
        {"agent": "news", "title": "GPT-5 Released by OpenAI", "importance": "high"},
        {"agent": "tools", "title": "GitHub Copilot Agent Mode", "importance": "high"},
        {"agent": "trends", "title": "Autonomous AI Agents in Production", "importance": "medium"},
        {"agent": "niche", "title": "Obscure Framework Update", "importance": "low"},
    ]

    user_prefs = [
        {"topic": "artificial intelligence", "weight": 2.0},
        {"topic": "developer tools", "weight": 1.5},
        {"topic": "machine learning", "weight": 1.0},
    ]

    result = evaluator.evaluate(sample, agent_reports, user_prefs)
    print(f"Evaluation result: {result}")

    # Verify all expected keys
    expected_keys = {"coverage", "dedup", "sources", "actionability", "length", "topic_balance", "overall"}
    assert set(result.keys()) == expected_keys, f"Missing keys: {expected_keys - set(result.keys())}"
    print("AC #1: All 7 score dimensions present")

    # All scores should be between 0 and 1
    for key, val in result.items():
        assert 0.0 <= val <= 1.0, f"{key} = {val} out of range"
    print("AC #2: All scores in [0.0, 1.0]")

    # Coverage: both high-importance stories (GPT-5, Copilot) are covered
    assert result["coverage"] >= 0.5, f"Coverage too low: {result['coverage']}"
    print(f"AC #3: Coverage = {result['coverage']}")

    # Dedup: sections are distinct
    assert result["dedup"] >= 0.8, f"Dedup too low: {result['dedup']}"
    print(f"AC #4: Dedup = {result['dedup']}")

    # Sources: 3 of 4 sections have URLs
    assert result["sources"] >= 0.5, f"Sources too low: {result['sources']}"
    print(f"AC #5: Sources = {result['sources']}")

    # Actionability: has why-it-matters, try-this, skills section
    assert result["actionability"] >= 0.5, f"Actionability too low: {result['actionability']}"
    print(f"AC #6: Actionability = {result['actionability']}")

    # Length check with known word count
    word_count = len(sample.split())
    print(f"AC #7: Word count = {word_count}, length score = {result['length']}")

    # Empty newsletter edge case
    empty_result = evaluator.evaluate("", [], [])
    assert all(0.0 <= v <= 1.0 for v in empty_result.values())
    print("AC #8: Empty newsletter handled gracefully")

    # Check _split_into_sections
    sections = _split_into_sections(sample)
    assert len(sections) >= 3, f"Expected 3+ sections, got {len(sections)}"
    print(f"AC #9: Section splitting found {len(sections)} sections")

    # Negative-weight and duplicate preferences should not break scoring
    adversarial_prefs = [
        {"topic": "artificial intelligence", "weight": 2.0},
        {"topic": "developer tools", "weight": 1.5},
        {"topic": "market news", "weight": -3.0},
        {"topic": "market news", "weight": -3.0},  # duplicate
        {"topic": "valuations and funding", "weight": -3.0},
        {"topic": "agent security", "weight": 1.0},
        {"topic": "agent security", "weight": 1.0},  # duplicate
    ]
    adversarial_result = evaluator.evaluate(sample, agent_reports, adversarial_prefs)
    assert 0.0 <= adversarial_result["topic_balance"] <= 1.0, (
        f"topic_balance out of bounds: {adversarial_result['topic_balance']}"
    )
    assert 0.0 <= adversarial_result["overall"] <= 1.0, (
        f"overall out of bounds: {adversarial_result['overall']}"
    )
    print(f"AC #10: Negative-weight prefs handled — topic_balance={adversarial_result['topic_balance']}, overall={adversarial_result['overall']}")

    # All-negative preferences should return 1.0 (nothing to match)
    all_negative = [
        {"topic": "market news", "weight": -3.0},
        {"topic": "valuations and funding", "weight": -3.0},
    ]
    neg_result = evaluator.evaluate(sample, agent_reports, all_negative)
    assert neg_result["topic_balance"] == 1.0, (
        f"All-negative prefs should yield 1.0, got {neg_result['topic_balance']}"
    )
    print(f"AC #11: All-negative prefs → topic_balance=1.0")

    db.close()
    print("\nAll evaluator.py checks passed.")
