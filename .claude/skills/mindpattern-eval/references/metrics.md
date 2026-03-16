# Evaluation Metrics Reference

## Coverage Score (0.0 - 1.0)

### Method
1. Fetch HN stories with 100+ points from last 24h
2. For each HN story, search our findings for title similarity > 0.7
3. Score = matched / total_hn_stories
4. Bonus: +0.1 if we found stories NOT on HN (unique value)

### Thresholds
- 0.8+ = Excellent coverage
- 0.6-0.8 = Good coverage
- 0.4-0.6 = Gaps in coverage
- <0.4 = Poor coverage, investigate broken agents

## Consistency Score (0.0 - 1.0)

### Method
1. Query finding counts per agent for the run date
2. Target: 8-15 findings per agent
3. Score = (agents_hitting_target / total_active_agents)

### Per-Agent Thresholds
- 10+ findings = Excellent
- 8-9 findings = Good
- 5-7 findings = Underperforming
- <5 findings = Needs investigation
- 0 findings = Broken

### Known Issues
- skill-finder gets no preflight data (by design) -- grade on curve
- arxiv-researcher may return 0 on weekends (arXiv doesn't publish)

## Newsletter Quality Score (0.0 - 2.0)

### Components (each 0.0 - 0.5)
1. **Word count**: 0.5 if 4000-5000 words, linear decay outside range
2. **Source diversity**: 0.5 if 15+ unique domains, proportional below
3. **Section coverage**: 0.5 if all sections with findings have content
4. **Dedup**: 0.5 minus 0.1 per duplicate story across sections

### Thresholds
- 1.5+ = Excellent newsletter
- 1.0-1.5 = Good newsletter
- 0.5-1.0 = Needs improvement
- <0.5 = Major quality issues

## Run-over-Run Comparison

### Method
1. Load scores from last 7 runs
2. Compute 7-day rolling average for each dimension
3. Compare today vs average
4. Flag regressions > 20%

### Trend Indicators
- "up" = today > 7-day avg by 10%+
- "stable" = within 10% of 7-day avg
- "down" = today < 7-day avg by 10%+
- "REGRESSION" = today < 7-day avg by 20%+

## Preflight Coverage (new)

### Method
1. Check preflight source_counts from traces.db
2. Verify all 8 sources returned data
3. Flag sources with 0 items

### Thresholds
- 8/8 sources = Full coverage
- 6-7/8 = Acceptable (some sources may be down)
- <6/8 = Investigate broken sources
