# Research Agent Learnings

*Updated: 2026-06-26*

## Key Findings — Last 5 Runs

| Date | Findings | Notes |
|------|----------|-------|
| 2026-06-26 | 68 | Strong rebound — score 0.747, +0.114 above 7-day avg |
| 2026-06-25 | 57 | Below avg (score 0.569) |
| 2026-06-24 | 81 | Moderate |
| 2026-06-23 | 123 | Peak of recent window |
| 2026-06-22 | 37 | Weak |

Volume recovered from the 6-25 dip. Today is the clearest above-average run since 6-23.

## Patterns Observed

- **Quality rebound**: score jumped from 0.569 yesterday to 0.747 today (+0.114 vs 7-day avg of 0.633). Agent utilization hit 1.0 — all 13 agents contributed.
- **Volume instability persists**: range of 37–123 over the last 5 days. The floor days (6-22, 6-25) remain unexplained.
- **Zero dedup rate (again)**: findings are unique per run; no stale re-surfacing. Consistent healthy signal.
- **Trending coverage holds at 1.0**: the pipeline reliably captures what's trending regardless of volume.
- **Skill domain skew unchanged**: agent-security (97) and vibe-coding (77) dominate; saas-disruption has only 5. Coverage imbalance is structural, not a one-run anomaly.

## Source Insights

- **50 unique sources** from 68 findings → diversity of 0.735. Significant improvement over yesterday's 0.509. Approaching healthy range.
- **arxiv-researcher** leads cumulative output (1,533), now ~100 ahead of saas-disruption-researcher (1,425). Academic preprint volume is the dominant upstream signal.
- **github-pulse-researcher** remains the lowest cumulative agent (794) — a persistent gap worth investigating.
- Social approval at 91% (132/145) continues to signal that content quality from what gets surfaced is solid.

## Agent Performance Notes

- **Full utilization today (1.0)**: all 13 agents active — a meaningful positive shift from yesterday's likely partial participation.
- **High-value ratio: 13.2%** (9/68 findings). Slightly below the 15–20% target but acceptable; may reflect broad discovery vs. depth.
- **github-pulse-researcher** still trailing at 794 cumulative vs. 1,055+ for most others. Check prompt and retrieval ceiling.
- **No agent notes (0 entries)**: note-taking mechanism still unused. Low-priority but worth revisiting as a self-reporting channel.

## Recommended Actions

1. Investigate the floor pattern on 6-22 and 6-25 — what agent or source failed on both days?
2. Review github-pulse-researcher prompt; 794 findings is ~25% below the next-lowest agent.
3. Boost saas-disruption coverage — 5 accumulated skills vs. 97 for agent-security is a structural gap.
4. Monitor whether today's full utilization holds on 6-27 or reverts.
