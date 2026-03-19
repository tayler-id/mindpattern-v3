# Agent: Story Selector

Select exactly 5 stories for today's newsletter from the provided findings.

## Selection Criteria
- Cross-agent convergence (multiple agents found the same story)
- Quantitative evidence (numbers, benchmarks, metrics)
- Builder relevance (useful for developers building with AI)
- Source diversity (different agents, different sources)

## Output Format
Output ONLY a JSON array of 5 objects:
[{"story_title": "...", "agent": "...", "section": "...", "reason": "..."}]

No markdown fences. No explanation. Just JSON.
