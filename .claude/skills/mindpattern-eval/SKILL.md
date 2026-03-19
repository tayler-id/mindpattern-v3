---
name: mindpattern-eval
description: |
  Evaluate mindpattern research pipeline runs. Use when the user asks to
  "evaluate the last run", "score the pipeline", "compare runs", "check
  quality", or after completing a pipeline run. Scores coverage, agent
  consistency, newsletter quality, and run-over-run trends. Can also
  diagnose why a run underperformed.
user-invocable: true
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
---

# Pipeline Evaluation

Evaluate the most recent (or specified) pipeline run across 4 dimensions.

## Quick Start

1. Find the latest run date: `ls -la reports/ramsay/ | tail -5`
2. Load findings: `python3 -c "import memory; db=memory.get_db('ramsay'); ..."`
3. Score each dimension (see references/metrics.md for formulas)
4. Compare against previous runs
5. Report findings with specific recommendations

## Evaluation Dimensions

### 1. Coverage Score
Did agents find the important stories? Compare against known-good sources.
- Fetch today's HN front page: `python3 tools/hn-fetch.py --min-points 100`
- Check how many HN top stories appear in our findings
- Score: (matched stories / total HN top stories)

### 2. Consistency Score
Did every agent pull its weight?
- Query: `SELECT agent, COUNT(*) as cnt FROM findings WHERE run_date = ? GROUP BY agent`
- Flag agents with < 5 findings (underperforming)
- Flag agents with 0 findings (broken)
- Score: (agents with 8+ findings / total agents)

### 3. Newsletter Quality
Is the newsletter comprehensive and well-sourced?
- Word count (target: 4000-4500)
- Source diversity (unique domains cited)
- Section coverage (how many sections have content)
- Duplicate stories (same story in multiple sections)
- Read the newsletter: `cat reports/ramsay/{date}.md`

### 4. Run-over-Run Trend
Is quality improving or regressing?
- Compare today's scores vs 7-day average
- Flag significant drops (>20% in any dimension)
- Check if prompt changes correlate with quality changes

## Output Format

```markdown
## Pipeline Evaluation: {date}

### Scores
| Dimension | Score | Trend | Notes |
|-----------|-------|-------|-------|
| Coverage | 0.XX | up/down/stable | ... |
| Consistency | 0.XX | up/down/stable | ... |
| Newsletter | 0.XX | up/down/stable | ... |
| Overall | 0.XX | up/down/stable | ... |

### Agent Performance
| Agent | Findings | Status |
|-------|----------|--------|
| ... | N | OK/UNDER/BROKEN |

### Recommendations
1. ...
2. ...
```

## Detailed Metrics

See [references/metrics.md](references/metrics.md) for exact formulas, thresholds, and scoring rubrics.
