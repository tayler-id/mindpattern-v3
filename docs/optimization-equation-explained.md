# The MindPattern Optimization Equation — Explained

## The Equation

```
H* = arg max_H E_{X~X, T~p_M(H,X)} [r(T, X)]
```

In proper notation:

$$H^* = \arg \max_H \; \mathbb{E}_{X \sim \mathcal{X},\; T \sim p_M(H, X)}\bigl[r(T, X)\bigr]$$

## Symbol-by-Symbol Breakdown

| Symbol | What It Means | Plain English |
|--------|--------------|---------------|
| **H** | The "harness" — the thing you're optimizing | System prompt, agent skill file, pipeline configuration |
| **H\*** | The **optimal** harness | The configuration that produces the best average output |
| **arg max_H** | "Find the H that maximizes..." | Search over all possible configurations |
| **E[...]** | Expected value (average) | Average across many runs with different inputs |
| **X ~ X** | Input X sampled from input distribution X | Today's news, today's papers, today's GitHub trending — different every day |
| **T ~ p_M(H, X)** | Output T sampled from model distribution p_M, conditioned on H and X | What Claude actually generates when given this skill file (H) and this input (X) |
| **p_M** | The model's output distribution | Claude's behavior — fixed, not something you can change |
| **r(T, X)** | Reward function — scores output T given input X | Quality score: was this newsletter good? Was this finding valuable? |

## Reading It as a Sentence

> "H-star is the harness configuration that maximizes the expected reward, where inputs are sampled from the real world and outputs are sampled from the model's behavior under that configuration."

Or even simpler:

> "Find the best system prompt such that, on average across all the inputs you'll encounter, the model produces the highest-quality output."

## Why This Equation Matters

The key insight is what you **can** and **cannot** control:

- **You cannot change p_M** — the model weights are fixed. Claude is Claude.
- **You CAN change H** — the prompts, skill files, configuration, and pipeline structure that wrap the model.
- **You cannot control X** — tomorrow's news is unknown. The optimization must work in expectation across all possible inputs, not just today's.

This means the optimization target is **the wrapper, not the model**. You're not fine-tuning Claude. You're finding the best instructions to give Claude.

## How MindPattern Implements This Equation

### Variable Mapping

| Equation Variable | MindPattern Equivalent | Where in Codebase |
|-------------------|----------------------|-------------------|
| **H** (harness) | Agent skill files + system prompts + config | `verticals/ai-tech/agents/*.md`, `prompts/*.md`, `agents/*.md`, `config.json` |
| **X** (inputs) | Daily preflight data — ~400 items from 8 sources | `preflight/run_all.py` fetches from RSS, HN, arXiv, GitHub, Reddit, Twitter, YouTube, LinkedIn |
| **p_M(H, X)** (model behavior) | Claude's output given skill file H and preflight data X | `orchestrator/agents.py` — `run_single_agent()` spawns `claude -p` subprocess |
| **T** (output) | Agent findings, newsletter text, social posts | Structured JSON findings, 4,500-word newsletter, platform-native posts |
| **r(T, X)** (reward) | Deterministic quality scoring — no LLM in the loop | `orchestrator/evaluator.py` — `NewsletterEvaluator.evaluate()` scores on 6 dimensions |
| **E[...]** (expectation) | Average quality across daily runs | `orchestrator/observability.py` — 7-day rolling average in `quality_history` table |
| **arg max_H** (search) | Three optimization loops searching for better H | `autoresearch.py`, `orchestrator/analyzer.py`, `harness/run.sh` |

### The Reward Function r(T, X) — In Detail

The reward isn't a single number. It's a weighted composite of 6 deterministic dimensions computed by `orchestrator/evaluator.py`:

| Dimension | Weight | What It Measures | How It's Computed |
|-----------|--------|-----------------|-------------------|
| **Coverage** | 0.25 | Do high-importance findings appear in the newsletter? | Keyword intersection: % of significant title words found in newsletter text |
| **Dedup** | 0.20 | Are newsletter sections unique from each other? | Pairwise section overlap — flags sections with >60% word overlap |
| **Sources** | 0.15 | Do sections cite their sources? | % of sections containing URLs |
| **Actionability** | 0.15 | Is the newsletter useful, not just informative? | Presence of "why it matters", "try this", action items, bullet points |
| **Length** | 0.10 | Is it the right length? | Word count within ideal range (1500-3000 words) |
| **Topic Balance** | 0.15 | Does it cover the user's interests? | Intersection with user preference topics |

```
r(T, X) = 0.25 * coverage + 0.20 * dedup + 0.15 * sources 
         + 0.15 * actionability + 0.10 * length + 0.15 * topic_balance
```

All values clamped to [0, 1]. No LLM involved — pure string matching, regex, and counting.

### The Social Pipeline Has Its Own r(T, X)

The social media pipeline has a separate reward function implemented across multiple agents:

| Gate | Scoring Method | Threshold |
|------|---------------|-----------|
| **EIC (Editor-in-Chief)** | LLM-scored: novelty (35%) + broad appeal (40%) + thread potential (25%) | Composite >= 5.0/10 |
| **Blind Critics** | LLM-scored: voice match, framing authenticity, platform genre fit, epistemic calibration, structural variation, rhetorical framework | 6 dimensions, 0-10 each |
| **Policy Validation** | Deterministic: character limits, banned words, rate limits, injection patterns | Hard pass/fail |
| **Expeditor** | LLM-scored: same 6 dimensions as critics, plus hard kill switches | Composite meets threshold; kill switches = automatic FAIL |

Kill switches that produce r = 0 regardless of other scores:
- Product pitch language ("powered by MindPattern")
- Banned words (delve, tapestry, multifaceted, testament, realm, landscape...)
- Factual errors or missing attribution
- "In conclusion" / "In summary" closings
- Multiple findings stacked without a connecting thread

## The Three Optimization Loops (How arg max_H Is Approximated)

The equation says "find the best H." In practice, you can't enumerate all possible skill files. MindPattern approximates the search with three complementary loops:

### Loop 1: autoresearch.py — Gradient-Free Hypothesis Testing

**When:** Nightly (separate launchd cron)  
**Mechanism:** Generate-test-adopt  
**Files it can modify:** `verticals/ai-tech/agents/*.md`, `prompts/*.md`, `config.json`

```
Current H (skill files) + quality context from memory.db
    |
    v
Generate 3 hypotheses for H' (via Opus)
    |
    v
For each hypothesis:
    Evaluate: would this H' beat H by >= 0.005 (0.5%)?
    |
    v
Adopt winning H', or keep H
```

The 0.5% threshold is essentially a significance test — "did this change to H actually improve expected reward, or was it noise from a lucky input distribution that day?"

**In equation terms:** This is hill-climbing in H-space. Each night, it proposes a small perturbation H' and accepts it only if E[r(T,X) | H'] > E[r(T,X) | H] + epsilon.

### Loop 2: orchestrator/analyzer.py — Trace-Driven Skill Refinement

**When:** During the EVOLVE phase of each pipeline run  
**Mechanism:** Compare observed agent behavior to intended behavior in skill files  
**Output:** JSON diff of skill file changes

```
Today's execution traces (per-agent)
    + Current skill files
    + Pipeline metrics
    + Regression warnings from prompt_tracker.py
    |
    v
Analyze deviations:
    - Tool usage order (did agent use Exa before WebSearch as instructed?)
    - Phase compliance (did agent evaluate preflight before exploring?)
    - Quality (deep reads vs. search snippet skimming?)
    - Output validity (valid JSON on first parse attempt?)
    - Cross-agent patterns (same mistake across multiple agents = systemic)
    |
    v
Output: { "changes": [...], "reversions": [...], "no_changes": [...] }
```

**In equation terms:** This is gradient estimation. By observing where agents deviate from H (the skill file instructions), it infers which parts of H are unclear or counterproductive, and proposes targeted edits.

### Loop 3: harness/run.sh — Bug-Driven Optimization

**When:** Runs as part of the autonomous harness  
**Mechanism:** Find where r(T,X) is low, diagnose root cause, fix the system  
**Output:** Git PRs that modify the pipeline code itself

```
Scout reads traces.db for failures + quality drops
    |
    v
Creates tickets targeting specific files
    |
    v
Fix agent (TDD): write failing tests, then implement
    |
    v
Deterministic gates: syntax, secrets, debug, diff scope, pytest
    |
    v
Review agent: 3 specialist sub-agents score quality
    |
    v
PR created if score >= 7/10
```

**In equation terms:** This optimizes the **infrastructure around H**, not H itself. If the reward is low because of a bug in how findings are parsed, or a race condition in agent dispatch, no amount of prompt optimization will fix it. The harness finds and fixes these structural issues.

## The Knowledge Graph: Memory for arg max_H

This is the piece that makes the optimization loops smarter over time. Without it, each loop iteration starts from scratch — the Scout re-reads every file, the analyzer has no context about past improvements, and autoresearch proposes the same failed hypotheses.

The knowledge graph (`harness/knowledge_graph.py`) is a **wiki-linked markdown knowledge base** that accumulates learnings across runs. It lives in `harness/knowledge/` as a set of interconnected markdown files:

### Structure

```
harness/knowledge/
    INDEX.md                        # Master index with [[wiki-links]] to all files
    issues-open.md                  # Current known bugs and fragile patterns
    patterns-what-works.md          # Approaches that produce high r(T,X)
    patterns-what-fails.md          # Anti-patterns that produce low r(T,X)
    runs-latest.md                  # Latest harness run outcomes
    orchestrator-runner.md          # Module knowledge: runner.py
    orchestrator-agents.md          # Module knowledge: agents.py
    orchestrator-evaluator.md       # Module knowledge: evaluator.py
    social-pipeline.md              # Module knowledge: social pipeline
    memory-findings.md              # Module knowledge: findings storage
    ... (31 files total, one per major module)
```

### Wiki-Link Resolution

Files are connected via `[[wiki-links]]` that resolve to other knowledge files:

```
[[orchestrator/runner]]    ->  knowledge/orchestrator-runner.md
[[issues/open]]            ->  knowledge/issues-open.md
[[patterns/what-works]]    ->  knowledge/patterns-what-works.md
```

The `check()` function validates all links resolve. The `expand(slug, depth)` function inlines linked content — like following hyperlinks and concatenating the pages.

### How It Evolves (The evolve() Function)

After each harness stage, `evolve(stage, data)` updates the knowledge files:

| Stage | Trigger | What Gets Updated |
|-------|---------|-------------------|
| `scout_done` | Scout creates new tickets | `issues-open.md` gets new "Scout Findings" section with ticket IDs, priorities, and affected files |
| `fix_done` | Fix agent completes (pass or fail) | `runs-latest.md` gets ticket outcome (passed/failed, PR URL, reason) |
| `review_done` | Review agent accepts or rejects | `patterns-what-works.md` (if merged) or `patterns-what-fails.md` (if rejected, with failure reason) |
| `run_complete` | Harness run finishes | `runs-latest.md` gets final summary (processed, PRs created, failed, remaining) |

After every evolution, `check()` re-validates all wiki-links and logs broken ones.

### How Agents Read the Knowledge Graph

The `summary()` function returns a compact bundle for injection into agent prompts:

```python
def summary() -> str:
    """Includes: shared issue log + INDEX + issues + patterns."""
    parts = []
    parts.append(ISSUES.md)           # Highest priority — what broke recently
    parts.append(INDEX.md)            # Module map with wiki-links
    parts.append(issues-open.md)      # Known bugs and fragile patterns
    parts.append(patterns-what-fails.md)  # Anti-patterns to avoid
    parts.append(patterns-what-works.md)  # Proven approaches
    parts.append(runs-latest.md)      # What happened last time
    return "\n".join(parts)
```

This summary is injected into the Scout prompt before it looks for issues. The result: the Scout doesn't re-discover known bugs, doesn't create duplicate tickets, and can build on proven patterns.

### What the Knowledge Graph Currently Knows

**What works (high r(T,X)):**
- 13 parallel agents with specialization: 230-254 findings per run consistently
- TDD in harness fix agents: catches regressions before merge
- Deterministic quality scoring: avoids burning LLM tokens on evaluation
- WAL mode for SQLite: enables concurrent reads during parallel agent writes
- Three-actor convergence rule: when 3+ sources report the same signal, social posts pass Gate 1 cleanly
- Staggered worktree creation: 5s delay prevents git config lock races

**What fails (low r(T,X)):**
- Research tickets that are too ambitious: M-effort features with external dependencies fail in 15 turns
- High max_turns: 40 turns on Opus burns tokens with no result. 15 turns forces focus or fast fail.
- Zero-findings systemic failure: Runs 12-13 produced nothing. Recovered Run 14 but root cause unknown.
- Sources score regression: drops to 0.333 when security topics dominate — structural issue in evaluator
- Migration ordering bugs: CREATE INDEX before ALTER TABLE ADD COLUMN crashes production databases
- Jina Reader errors passing through as content: curl exits 0 even when Jina returns error JSON

**Known open issues (preventing higher r(T,X)):**
- Missing DB tables in memory/db.py — 4 tables referenced by code but never created in schema init
- Topic score stuck at 0 for 7+ consecutive runs
- Gate 1 silently auto-approves on exception
- Thread safety in embeddings module (module-level singleton not thread-safe)
- No transaction boundaries in findings storage (crash between statements = orphaned rows)

### The Knowledge Graph's Role in the Equation

In equation terms, the knowledge graph is the **memory that makes arg max_H efficient**.

Without it, each optimization iteration is independent — the system has no way to remember that "research tickets with 5+ files always fail" or that "staggering worktree creation fixed the lock race." It would keep re-discovering these facts.

With it, the search space for H narrows over time:

```
Day 1:  H_space = all possible configurations
        Knowledge graph = empty
        Scout searches blindly, creates redundant tickets

Day 30: H_space = configurations consistent with 30 days of learnings
        Knowledge graph = 31 files, 50+ patterns, 100+ ticket outcomes
        Scout reads summary(), avoids known failures, builds on proven patterns
```

The knowledge graph doesn't change the equation — H* is still the optimal configuration. But it changes the **efficiency of the search** for H*. Instead of random exploration, the system does informed exploration guided by accumulated evidence.

### The Full Optimization Architecture

Putting it all together:

```
                   +-----------------------+
                   |   The Equation        |
                   |   H* = arg max_H      |
                   |   E[r(T, X)]          |
                   +-----------+-----------+
                               |
              "Find best H that maximizes
               average quality score"
                               |
            +------------------+------------------+
            |                  |                  |
            v                  v                  v
    +-------+------+   +------+-------+   +------+-------+
    | autoresearch |   | analyzer.py  |   | harness/     |
    | .py          |   |              |   | run.sh       |
    +-------+------+   +------+-------+   +------+-------+
    |               |   |               |   |               |
    | Modify H:     |   | Modify H:     |   | Modify infra: |
    | skill files,  |   | skill files   |   | pipeline code,|
    | prompts,      |   | based on      |   | bug fixes,    |
    | config        |   | trace analysis|   | new features  |
    +-------+------+   +------+-------+   +------+-------+
            |                  |                  |
            +------------------+------------------+
                               |
                               v
                   +-----------+-----------+
                   |  Knowledge Graph      |
                   |  harness/knowledge/   |
                   |                       |
                   |  Remembers:           |
                   |  - What works (H+)    |
                   |  - What fails (H-)    |
                   |  - Known issues       |
                   |  - Module knowledge   |
                   |  - Run outcomes       |
                   |                       |
                   |  Feeds back into all  |
                   |  three loops via      |
                   |  summary() injection  |
                   +-----------+-----------+
                               |
                   +-----------+-----------+
                   |  Daily Pipeline Run   |
                   |  orchestrator/runner  |
                   |                       |
                   |  X ~ preflight data   |
                   |  T ~ claude output    |
                   |  r(T,X) ~ evaluator   |
                   |                       |
                   |  Produces the signal  |
                   |  all three loops      |
                   |  optimize against     |
                   +-----------------------+
```

## Why This Architecture Is Interesting

1. **The model is a black box.** MindPattern never fine-tunes Claude. It optimizes what it can control: the wrapper (H).

2. **The reward is deterministic.** No LLM in the evaluation loop means no prompt injection can game the quality score. The evaluator is pure Python: string matching, regex, counting.

3. **The search is multi-modal.** Three different loops attack the optimization from different angles: prompt perturbation (autoresearch), behavioral trace analysis (analyzer), and infrastructure debugging (harness). They're complementary — not redundant.

4. **The knowledge graph is the accumulator.** Without it, each optimization iteration is memoryless. With it, the system builds up an institutional understanding of what works and what doesn't, making future iterations more efficient.

5. **The intractable expectation is approximated by daily runs.** You can't compute E[r(T,X)] analytically — the input distribution changes daily. So the system runs every day, measures reward on that day's actual inputs, and trends the 7-day rolling average. Over time, the law of large numbers makes this approximation converge.

6. **The 0.5% threshold is a significance test.** autoresearch.py only adopts changes that beat baseline by 0.005. This prevents overfitting to one day's lucky input distribution. It's the equivalent of a p-value check in a clinical trial.

## Open Questions

1. **Is the reward function aligned?** The evaluator measures coverage, dedup, sources, actionability, length, and topic balance. But does maximizing these dimensions actually produce newsletters that humans want to read? The weights (0.25, 0.20, 0.15, 0.15, 0.10, 0.15) are hand-tuned, not learned.

2. **Is the search exploring enough?** autoresearch tests 3 hypotheses per night. With a 0.5% improvement threshold, it's conservative — unlikely to make large jumps. Is it stuck in a local optimum?

3. **Does the knowledge graph prune aggressively enough?** Patterns from Run 12 may not apply at Run 50. The knowledge files grow monotonically — there's no decay or garbage collection on stale patterns.

4. **Is cross-agent dedup at the right threshold?** The system uses 85% cosine similarity for cross-agent dedup, 80% for social dedup, 90% for finding dedup, and 75% for patterns. These are all hardcoded. Are they optimal?

5. **Can the three loops interfere destructively?** If autoresearch changes a skill file on Tuesday night, and the analyzer proposes reverting it on Wednesday because traces look different, and the harness creates a ticket to "fix" the regression — all three loops could fight each other. Is there coordination?
