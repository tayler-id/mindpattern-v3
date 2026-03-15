# Self-Applicable Research Catalog

> Research from mindpattern newsletters (Run 1–45) that can be applied back to improve the mindpattern system itself.
> Generated 2026-03-14 from exhaustive analysis of all 24 newsletters.
> **266 findings** across 4 system areas.

---

## How to Use This Document

Each finding includes:
- **Newsletter date** and section where it was found
- **What it is** — the specific research, tool, paper, or technique
- **How it applies** — exactly where in the mindpattern pipeline this could be used
- **Which component** it improves

Findings are organized by system component, then by category.

---

# PART 1: RESEARCH AGENTS (65+ Findings)

The 13 agents that gather information: news-researcher, agents-researcher, vibe-coding-researcher, thought-leaders-researcher, projects-researcher, sources-researcher, skill-finder, arxiv-researcher, github-pulse-researcher, hn-researcher, reddit-researcher, rss-researcher, saas-disruption-researcher.

## 1.1 Context Engineering & Prompt Optimization

### Context Engineering Over Prompt Engineering
- **Date**: 2026-02-12, Vibe Coding
- **What**: Anthropic's Context Engineering Guide. Maintain lightweight identifiers and dynamically load data via tools at runtime. Sub-agents should return condensed 1–2K token summaries.
- **Applies to**: ALL 13 agents
- **How**: Each researcher agent should return condensed 1-2K token summaries for the synthesizer. Orchestrator maintains lightweight identifiers and loads full content on demand. Saves 30%+ on token costs.

### AGENTS.md Instruction Compliance Crisis (IFScale)
- **Date**: 2026-03-03, Top 5 (#1)
- **What**: Distyl AI's IFScale benchmark. Best LLM follows only 68% of instructions at 500 lines. Google's "repetition hack" (critical rules at beginning AND end) boosts compliance from 21% to 97%.
- **Applies to**: ALL 13 agents (system prompts)
- **How**: Audit every agent's prompt. If any exceed 100 lines, prune. Place 5 most critical rules (dedup, source quality, novelty) in lines 1-10 AND duplicate at end. Positive framing over negative.

### Chain-of-Draft Prompting (70-90% Token Reduction)
- **Date**: 2026-02-16, Best Content
- **What**: arXiv 2502.18600. "Write only the minimum draft for each reasoning step." Max 5 words per step. 70-90% token reduction vs CoT.
- **Applies to**: ALL 13 agents, especially arxiv-researcher, sources-researcher
- **How**: Replace CoT prompts with Chain-of-Draft for massive token savings on reasoning-heavy agents.

### Prompt Caching Architecture
- **Date**: 2026-02-21, Top 5 (#5) and Best Content
- **What**: arXiv 2601.06007v1. System-prompt-only caching is optimal. Claude: 78.5% cost savings + 22.9% latency improvement. Keep timestamps and dynamic data OUTSIDE cacheable prefix.
- **Applies to**: ALL 13 agents
- **How**: Structure agent prompts static-first. Cache stable system prompt and tool definitions. Exclude dynamic tool results. Monitor cache hit rates above 80%.

### Sub-Agent Compression Pattern
- **Date**: 2026-02-27, Skills (#5)
- **What**: Each sub-agent explores freely but returns only 1-2K condensed summary. Anthropic's system showed 90.2% performance improvement despite 15x more total tokens.
- **Applies to**: Orchestrator coordinating all 13 agents
- **How**: Each research agent compresses findings to 1-2K summaries for the synthesizer. Full content available on demand.

### Mermaid Diagrams for 5x Context Compression
- **Date**: 2026-03-13, Skills (#6)
- **What**: Replace prose descriptions with Mermaid diagrams. ~2K tokens vs ~10K for equivalent understanding.
- **Applies to**: ALL 13 agents (system prompt optimization)
- **How**: Replace prose pipeline descriptions in agent configs with Mermaid flowcharts.

## 1.2 Search & Information Retrieval

### PageIndex — Vectorless RAG (98.7% Accuracy)
- **Date**: 2026-02-23, Hot Projects; 2026-02-28 (19.3K stars)
- **What**: VectifyAI/PageIndex. Hierarchical tree indexing + LLM reasoning. 98.7% accuracy on FinanceBench. No chunking, no vector DB. MCP server.
- **Applies to**: sources-researcher, arxiv-researcher, news-researcher
- **How**: Replace vector similarity search for dedup/retrieval with hierarchical tree approach. Better "was this already covered?" detection.

### LEANN — Vectorless RAG with 97% Storage Savings
- **Date**: 2026-02-25, Hot Projects (10.1K stars)
- **What**: Graph-based selective recomputation. On-demand embeddings. Scales to 60M docs on laptop. MCP server.
- **Applies to**: ALL 13 agents (cross-run memory and dedup)
- **How**: Graph-based on-demand embeddings eliminate vector database storage while improving retrieval quality.

### Search More, Think Less (SMTL)
- **Date**: 2026-03-01, Research Papers
- **What**: arXiv 2602.22675. Parallel evidence acquisition replaces sequential reasoning. 70.7% fewer reasoning steps. SOTA on BrowseComp (48.6%), GAIA (75.7%), Xbench (82.0%).
- **Applies to**: ALL 13 agents (search strategy)
- **How**: Restructure agents to do parallel search queries first, then reason over gathered evidence. Fewer steps, better results.

### tobi/qmd — On-Device Search Engine with MCP
- **Date**: 2026-02-17, Hot Projects (9.1K stars)
- **What**: Built by Tobias Lutke (Shopify). BM25 + vector semantic search + LLM re-ranking, all local. MCP server.
- **Applies to**: ALL 13 agents (searching past findings database)
- **How**: Hybrid BM25 + vector + LLM re-ranking for querying findings database. Dramatically better dedup detection.

### GraphRAG Hybrid Retrieval
- **Date**: 2026-02-13, Skills (#9)
- **What**: Vector similarity + knowledge graph traversal. Microsoft GraphRAG reference implementation. 30-50% better retrieval on multi-hop questions.
- **Applies to**: sources-researcher, news-researcher
- **How**: Knowledge graph of entities (companies, people, papers, tools) across all findings. Agents traverse graph to find related prior coverage.

## 1.3 Dedup & Content Filtering

### Cross-Agent Deduplication Gap (Self-Identified)
- **Date**: 2026-02-12, Meta section
- **What**: "Cross-agent deduplication — Anthropic $30B and OpenClaw were covered by 3+ agents each."
- **Applies to**: Orchestrator
- **How**: Share "already covered" entity list from completed agents before each new agent runs.

### SkillsBench: Curated Content Beats Auto-Generated
- **Date**: 2026-02-17, Vibe Coding
- **What**: 86 tasks, 7,308 trajectories. Curated skills +16.2%, self-generated skills +0%.
- **Applies to**: ALL 13 agents
- **How**: Hand-craft high-quality search queries and evaluation rubrics per agent. Don't let agents auto-generate their own.

### Skills Analysis: 46.3% Duplicate Rate
- **Date**: 2026-02-24, Skills (#6)
- **What**: HuggingFace analysis. 46.3% agent skills are duplicates.
- **Applies to**: Findings dedup across 13 agents
- **How**: Semantic dedup at findings level — not just exact-match but similarity scoring to catch near-duplicates from different source angles.

## 1.4 Source Quality & Evaluation

### DREAM Framework for Research Agent Evaluation
- **Date**: 2026-02-25, Best Content
- **What**: arXiv 2602.18940 (AWS). Metrics for multi-turn reasoning, tool use patterns, and research quality. Designed for deep research agents.
- **Applies to**: ALL 13 agents
- **How**: This IS the benchmark for the newsletter's research agents. Adopt DREAM's metrics: breadth of sources, depth of analysis, novelty of findings, accuracy of claims.

### Agent Reliability: 12 Metrics, 4 Dimensions
- **Date**: 2026-02-28, Best Content
- **What**: arXiv 2602.16666. Consistency, robustness, predictability, safety. Stronger benchmarks ≠ reliable real-world operation. Prompt robustness is key.
- **Applies to**: ALL 13 agents
- **How**: Measure each agent's reliability across 4 dimensions. Focus on prompt robustness: consistent quality across different topics.

### Black-Box Reliability Certification
- **Date**: 2026-02-28, Best Content
- **What**: arXiv 2602.21368. Single reliability number per system-task pair via self-consistency sampling + conformal calibration. Sequential stopping reduces costs ~50%.
- **Applies to**: ALL 13 agents
- **How**: Run each agent 3-5 times on same query, measure self-consistency. Use reliability score to weight agent contributions.

### Longer CoT Negatively Correlated with Accuracy
- **Date**: 2026-03-01, Research Papers
- **What**: Google. r = -0.54 to -0.59 between token count and accuracy across 8 models. "Deep-Thinking Ratio" metric.
- **Applies to**: ALL 13 agents
- **How**: Monitor response length. Excessively long reasoning chains = lower-quality output. Set max response length constraints.

## 1.5 Web Scraping & Data Extraction

### Scrapling v0.4 — Adaptive Web Scraping with MCP (15.2K stars)
- **Date**: 2026-02-25, Hot Projects
- **What**: 774x faster than BeautifulSoup+Lxml. Parser learns from website changes. MCP server. Cloudflare Turnstile bypass. Concurrent spider.
- **Applies to**: news-researcher, sources-researcher, rss-researcher
- **How**: Drop-in replacement for current scraping. Adaptive parsing means agents don't break when websites change layout. MCP integration plugs directly into pipeline.

### Google LangExtract — Open-Source Document Extraction
- **Date**: 2026-02-12, Hot Projects (28.4K stars)
- **What**: Gemini-powered structured extraction with source grounding. Maps every extraction to exact location.
- **Applies to**: sources-researcher, arxiv-researcher
- **How**: Extract structured findings (paper name, star count, key metric, date) from unstructured web pages and PDFs.

### WebMCP — 89% Token Efficiency Over Screenshot Automation
- **Date**: 2026-02-12 (first mention), 2026-02-26 (Chrome ships)
- **What**: Chrome 146 ships WebMCP. Websites expose structured data to agents. 89% fewer tokens vs screenshot workflows.
- **Applies to**: news-researcher, hn-researcher, reddit-researcher
- **How**: As WebMCP adoption grows, access structured data directly instead of scraping HTML.

### CLI vs MCP — 94% Token Savings
- **Date**: 2026-02-26, Hot Projects
- **What**: CLIHub. 94% token savings by replacing MCP tool schemas with CLI wrappers.
- **Applies to**: ALL 13 agents
- **How**: Wrap some MCP tools as CLI commands to save context window space.

### Context Mode MCP — 98% Context Reduction
- **Date**: 2026-03-01, Hot Projects (423 HN points)
- **What**: Isolated sandbox processing. 315 KB → 5.4 KB (98% compression). Session length: ~30min → ~3hrs.
- **Applies to**: ALL 13 agents (processing large web pages)
- **How**: Compress web page content before feeding to agent reasoning. Dramatically extends how many sources each agent can process per run.

## 1.6 Agent Memory & Cross-Run Persistence

### EchoVault — Persistent Local Memory for Coding Agents
- **Date**: 2026-02-25, Vibe Coding
- **What**: MCP server with memory_context, memory_search, memory_save. Markdown vault + SQLite FTS5 + optional semantic search. Zero RAM at idle.
- **Applies to**: ALL 13 agents
- **How**: Each agent remembers which sources were productive last run, which queries returned nothing, what topics are trending up/down over time.

### Mastra Observational Memory
- **Date**: 2026-02-13, Skills (#8)
- **What**: Observes interactions, automatically extracts persistent facts without explicit save commands.
- **Applies to**: ALL 13 agents
- **How**: Auto-extract patterns: "HN stories with 200+ points are always worth covering" or "arXiv papers with 30+ HuggingFace upvotes correlate with Top 5 placement."

### OpenViking — Filesystem Context Database (ByteDance)
- **Date**: 2026-03-01, Hot Projects; 2026-03-14 (9.8K stars)
- **What**: Hierarchical filesystem paradigm. L0/L1/L2 tiered loading. Auto-extracts long-term memory.
- **Applies to**: ALL 13 agents (memory architecture)
- **How**: L0 (always loaded: agent identity, core rules), L1 (on demand: recent findings, trending topics), L2 (specific query: historical database).

### Hindsight — Biomimetic Agent Memory
- **Date**: 2026-03-14, Hot Projects (3.9K stars)
- **What**: World Facts, Experiences, Mental Models. SOTA on LongMemEval. Fortune 500 production.
- **Applies to**: ALL 13 agents
- **How**: Facts = known entities, star counts, dates. Experiences = what worked/didn't in past searches. Mental Models = rules like "Chinese lab releases cluster around holidays."

### Memory-R1: RL-Based Agent Memory Management
- **Date**: 2026-03-03, Best Content
- **What**: arXiv 2508.19828. ADD/UPDATE/DELETE operations via RL agents. 152 training QA pairs outperforms baselines.
- **Applies to**: ALL 13 agents
- **How**: Instead of accumulating all findings forever, use memory management that prunes, updates, consolidates findings over time.

## 1.7 Multi-Agent Coordination

### MIT EnCompass Framework — Beam Search for Agents
- **Date**: 2026-02-12, Agent Ecosystem
- **What**: Separates search strategy from workflow logic. Auto-backtracks on errors. 15-40% accuracy, 82% code reduction.
- **Applies to**: Orchestrator
- **How**: Ambiguous/low-confidence results → spawn parallel searches with different query formulations, take best result.

### Recursive Sub-Agent Delegation (ARC-AGI-2 Winner)
- **Date**: 2026-02-24, Top 5 (#2)
- **What**: Symbolica Agentica. 85.28% on ARC-AGI-2. Sub-agents spawn sub-agents, each with scoped context. Avg 2.6 agents per task.
- **Applies to**: Complex multi-domain findings
- **How**: When a finding spans domains (security tool + vibe coding), primary agent delegates deep investigation to a focused sub-agent.

### PCAS: Policy Compiler for Secure Agentic Systems
- **Date**: 2026-02-21, Research Papers
- **What**: arXiv 2602.16708. Deterministic policy enforcement via dependency graphs + reference monitor. Compliance: 48% → 93%.
- **Applies to**: Orchestrator (rule enforcement)
- **How**: Deterministic enforcement (not LLM-based) for dedup rules, source diversity requirements, output format compliance.

### AgentDropoutV2: Pruning for Multi-Agent Error Propagation
- **Date**: 2026-02-27, Research Papers
- **What**: arXiv 2602.23258. "Rectify-or-reject" pruning between handoffs. Prevents cascading errors.
- **Applies to**: Synthesis pipeline
- **How**: Quality gates between each agent's output and synthesizer. Bad/off-topic findings get pruned before contamination.

### Self-Healing Router: 93% Fewer LLM Calls
- **Date**: 2026-03-03, Research Papers
- **What**: arXiv 2603.01548. Agent control-flow as routing, not reasoning. 9 LLM calls vs 123 for ReAct.
- **Applies to**: Agent orchestration
- **How**: When a source/API fails (broken RSS feed), auto-reroute to alternative sources without spending tokens on reasoning about the failure.

### Deterministic Orchestration > Agent Self-Direction (McKinsey)
- **Date**: 2026-02-27, Best Content
- **What**: Deterministic state machine transitions outperform autonomous orchestration, which "routinely skipped steps, created circular dependencies, or got stuck."
- **Applies to**: Orchestrator design
- **How**: Deterministic state machine (query → search → filter → evaluate → rank → output) instead of agent self-direction.

## 1.8 Specific Agent Source Gaps

### Reddit API Integration
- **Date**: 2026-02-12, Meta
- **What**: "Reddit communities not deeply mined. Web search can't reliably access Reddit; API integration needed."
- **Applies to**: reddit-researcher
- **How**: Use Reddit API with min-score filtering (confirmed working 2026-02-28).

### YouTube Data API
- **Date**: 2026-02-12, Meta
- **What**: "No video content surfaced despite 7 channels tracked."
- **Applies to**: sources-researcher
- **How**: YouTube Data API to check new uploads from tracked channels (Matthew Berman, Fireship, AI Explained, etc.).

### Twitter/X Monitoring
- **Date**: 2026-02-12 through 2026-03-14 (recurring)
- **What**: "Systematic Twitter monitoring still missing."
- **Applies to**: thought-leaders-researcher
- **How**: X API or rohunvora/x-research-skill MCP (2026-02-22, Hot Projects).

### Three-Pass Query Methodology for HN
- **Date**: 2026-02-28, Meta
- **What**: "hn-researcher 10 stories vs 1 last run — three-pass methodology working."
- **Applies to**: hn-researcher → apply to other agents
- **How**: Document and apply multi-pass approach across other agents.

### GitHub Query Bug Fix
- **Date**: 2026-02-27, Meta
- **What**: "GitHub fetcher + between qualifiers got double-encoded. Fixed by changing to spaces."
- **Applies to**: github-pulse-researcher
- **How**: Already fixed but highlights need for automated testing of API query construction.

## 1.9 Structured Output & Tool Design

### MCP Tool Descriptions Study
- **Date**: 2026-02-26, Best Content
- **What**: arXiv 2602.14878. 856 tools across 103 servers. Six key components of effective descriptions. Poor descriptions → agents misunderstand tools.
- **Applies to**: ALL 13 agents
- **How**: Audit tool descriptions. Follow the six components. Poor descriptions cause tool misuse.

### Phil Schmid MCP Best Practices
- **Date**: 2026-02-17, Best Content
- **What**: Outcomes Over Operations, Flatten Arguments (agents hallucinate nested dicts 40%+), 5-15 tools per server, Name for Discovery, Paginate Everything.
- **Applies to**: ALL 13 agents
- **How**: Keep each agent's tool count to 5-15. Flatten all argument structures. Rich docstrings.

## 1.10 Fine-Tuning & Model Optimization

### Fine-Tuning with RAG → Distilled Knowledge (ICLR 2026)
- **Date**: 2026-02-21, Research Papers
- **What**: arXiv 2510.01375. 4-stage pipeline converting RAG into learned competence. 91% success without retrieval (vs 82% with RAG). 10-60% fewer tokens.
- **Applies to**: Hypothetical fine-tuning
- **How**: Train specialized model that has internalized common research patterns, eliminating retrieval overhead.

### SWE-grep: RL-Specialized Subtask Models
- **Date**: 2026-03-12, Vibe Coding
- **What**: Cognition's SWE-grep-mini. 2,800+ tokens/sec (20x faster than Haiku) with equivalent accuracy for code search. Multi-turn RL for one subtask.
- **Applies to**: Specific pipeline stages
- **How**: Train small fast models for dedup detection ("is this finding novel?") or source quality scoring ("is this primary?").

### Autoresearch Pattern (Karpathy/Lutke)
- **Date**: 2026-03-13 and 2026-03-14
- **What**: 89 ML experiments in 7.5 hours. Git commits as persistent memory. Lutke: 93 commits, 53% faster.
- **Applies to**: Meta-improvement of system
- **How**: Overnight experiments testing different agent prompts, search queries, configurations. Measure quality, keep improvements.

---

# PART 2: SYNTHESIS & NEWSLETTER GENERATION (50 Findings)

How 13 agent reports become one newsletter. Includes dedup, prioritization, narrative threading, quality evaluation, self-improvement, and feedback loops.

## 2.1 Multi-Document Synthesis & Deduplication

### Sub-Agent Compression Pattern
- **Date**: 2026-02-12, 2026-02-27
- **What**: 1-2K token summaries, not full results. 90.2% performance improvement.
- **Applies to**: Synthesis input processing
- **How**: Enforce structured JSON per agent: headline, significance_score (1-10), source_urls, unique_contribution, 100-word summary. Synthesizer operates on these, not free-form text.

### Context Mode MCP — 98% Context Reduction
- **Date**: 2026-03-01, Hot Projects
- **What**: 315 KB → 5.4 KB. Session length: ~30min → ~3hrs.
- **Applies to**: Synthesis input processing
- **How**: Compression/extraction pass between agent reports and synthesis. Extract only novel findings, discard boilerplate.

### PageIndex — Vectorless RAG via Hierarchical Tree Indexing
- **Date**: 2026-02-23, 2026-02-28 (19.3K stars)
- **What**: 98.7% accuracy on FinanceBench. Tree indexing > vector similarity.
- **Applies to**: Cross-referencing 13 agent reports
- **How**: Index findings into hierarchical tree by topic/category. Traverse tree to identify merge candidates.

### Coverage Manifest Before Synthesis
- **Date**: 2026-02-17, Meta
- **What**: System noted "Reduced repetition via memory context overlap warnings."
- **Applies to**: Synthesis pipeline
- **How**: Before synthesis, generate a coverage manifest: all unique stories with contributing agents. Synthesizer uses manifest, not raw reports.

## 2.2 Content Prioritization & Ranking

### User Preference Weighting in Synthesis
- **Date**: 2026-02-13 through 2026-03-14 (throughout)
- **What**: Preference weights (agent security +2.0, vibe coding +1.5, market news -1.0).
- **Applies to**: Story selection and space allocation
- **How**: `story_priority = base_importance * topic_weight * recency_factor * uniqueness_score`. Allocate word count proportional to priority.

### Self-Consistency for Top 5 Selection
- **Date**: 2026-02-13, Skills (#2)
- **What**: Generate 5+ responses, take majority. 20-40% hallucination reduction.
- **Applies to**: Top 5 story ranking
- **How**: Generate 3-5 independent Top 5 rankings, select stories appearing in majority. Reduces risk of a bad synthesis distorting the newsletter.

### Windsurf Arena Mode — A/B Testing
- **Date**: 2026-02-23, Vibe Coding
- **What**: Two agents on same prompt, hidden identities, vote on better.
- **Applies to**: Synthesis quality
- **How**: Run parallel synthesis passes with different approaches, evaluator picks best.

## 2.3 Quality Evaluation (LLM-as-Judge)

### Post-Synthesis Evaluation Agent
- **Date**: 2026-02-24, Breaking News (Cursor Multi-Agent Judging)
- **What**: Auto-evaluates parallel runs, recommends best with explanation.
- **Applies to**: Newsletter quality
- **How**: After synthesis, evaluator scores on: coverage completeness, dedup quality, narrative coherence, actionability, length compliance.

### NeMo Evaluator LLM-as-Judge Pipeline
- **Date**: 2026-02-27, Skills
- **What**: Docker Compose, JSONL datasets, 5 scoring dimensions, CI/CD integration.
- **Applies to**: Newsletter quality CI
- **How**: Define dimensions: information completeness, dedup quality, narrative coherence, actionability, length, source attribution, topic balance.

### Braintrust LLM Evaluation CI/CD
- **Date**: 2026-02-26, Skills
- **What**: Free-tier (1M traces/month). Data + Task + Scorers.
- **Applies to**: Synthesis quality gates
- **How**: 10-20 reference newsletters rated excellent as evaluation baselines.

### Reasoning LLMs-as-Judges Can Be Gamed
- **Date**: 2026-03-14, Research Papers
- **What**: arXiv 2603.12246. Same model for synthesis and evaluation creates self-reinforcing bias.
- **Applies to**: Quality evaluation
- **How**: Use a DIFFERENT model for evaluation than synthesis. Or structural/deterministic checks alongside LLM evaluation.

### Black-Box Reliability Certification
- **Date**: 2026-02-28, 2026-03-01
- **What**: arXiv 2602.21368. Single reliability number via self-consistency sampling.
- **Applies to**: Synthesis consistency
- **How**: Run 3 synthesis passes, compare outputs, flag sections with high variance for human review.

## 2.4 Narrative Structure & Length Control

### Newsletter Spec Document
- **Date**: 2026-02-20, 2026-02-23, 2026-03-13 (Spec-Driven Development pattern)
- **What**: Specifications replace prompts as source of truth.
- **Applies to**: Synthesis structure
- **How**: Create NEWSLETTER_SPEC.md: exact sections, word count targets, required elements, narrative threading requirements.

### TDD for Content (Willison Pattern)
- **Date**: 2026-02-23, 2026-02-24, 2026-02-26
- **What**: Write tests first, then implement. Applied to content: define quality criteria before generation.
- **Applies to**: Newsletter quality
- **How**: Assertions: "Top 5 must each have 2+ source URLs," "No story in more than one section," "Every skill has difficulty level and source link," "Total word count between X and Y."

### Two-Pass Synthesis with Progressive Disclosure
- **Date**: 2026-02-12 (Claude Code Skills), 2026-02-17 (MCP Progressive Discovery)
- **What**: Scan metadata first, load full content only when matched.
- **Applies to**: Synthesis efficiency
- **How**: Pass 1: read 100-word summaries from each agent for story selection/ranking. Pass 2: load full details only for selected stories.

### Context Engineering Four-Technique Stack
- **Date**: 2026-02-28, Skills
- **What**: Offloading, Reduction, Retrieval, Isolation. 26-54% token reduction.
- **Applies to**: Synthesis pipeline
- **How**: Split synthesis into per-section calls, each receiving only relevant findings, shared editorial guidelines in cached prefix.

### Instruction Compliance — Keep Under 50 Lines
- **Date**: 2026-03-03, Top 5
- **What**: 68% compliance at 500 lines. Front-load and back-load critical rules.
- **Applies to**: Synthesis prompt
- **How**: Prune synthesis prompt to under 50 lines. Top 5 editorial rules at positions 1-10 AND at the end.

## 2.5 Self-Improvement & Learning Mechanisms

### Autoresearch Self-Improvement Loop
- **Date**: 2026-03-13, 2026-03-14 (Karpathy/Lutke)
- **What**: 89 experiments in 7.5 hours. Git commits as persistent memory.
- **Applies to**: System-level optimization
- **How**: Run autoresearch on synthesis quality: test different prompt variations, section orderings, length targets overnight. Measure quality, adopt best config.

### RetroAgent — Learning from Failures
- **Date**: 2026-03-12, Research Papers
- **What**: Lesson-memory buffer distilling reusable lessons from failures. +18.3% ALFWorld, +27.1% Sokoban.
- **Applies to**: Run-to-run improvement
- **How**: After negative feedback, generate "failure lesson" explaining what went wrong. Store in persistent buffer.

### Memory-R1: RL-Based Memory Management
- **Date**: 2026-03-03, Best Content
- **What**: arXiv 2508.19828. ADD/UPDATE/DELETE via RL agents. 152 training QA pairs.
- **Applies to**: Learnings management
- **How**: Structured learning storage with ADD/UPDATE/DELETE. System evaluates after each run what to keep/update/discard.

### Fine-Tuning via RAG Distillation
- **Date**: 2026-02-21, Research Papers
- **What**: arXiv 2510.01375. 91% success without retrieval (vs 82% with RAG). 10-60% fewer tokens.
- **Applies to**: Accumulated learnings
- **How**: Every 10 runs, distill accumulated learnings directly into editorial guidelines, removing retrieval need.

### HCAPO — Hindsight Credit Assignment
- **Date**: 2026-03-12, Research Papers
- **What**: LLM as post-hoc critic for step-level Q-values. +7.7% WebShop, +13.8% ALFWorld.
- **Applies to**: Post-run evaluation
- **How**: After each run, evaluator reviews final newsletter, identifies over/under-covered stories, generates specific improvement suggestions.

### DPO Fine-Tuning Pipeline
- **Date**: 2026-02-13, Skills
- **What**: SFT → generate pairs → human rank → DPO. Replacing RLHF.
- **Applies to**: Quality optimization
- **How**: Generate A/B pairs of newsletter sections, user ranks, accumulate preferences for synthesis prompt refinement.

### Evaluating Stochasticity in Deep Research Agents
- **Date**: 2026-02-28, Research Papers
- **What**: arXiv 2602.23271. Three variance sources. 22% stochasticity reduction via structured output formatting + ensemble queries.
- **Applies to**: Synthesis consistency
- **How**: Enforce structured output schemas for synthesis step. JSON schemas per section before expanding to prose. Reduces variance.

### Feedback Loop Extension
- **Date**: Throughout all newsletters
- **What**: Current loop adjusts research weights but may not adjust synthesis behavior.
- **Applies to**: Section-level tuning
- **How**: If users say "Top 5 was great" → increase word count. "Too long" → reduce. Track per-section satisfaction.

## 2.6 Multi-Agent Deliberation for Synthesis

### Deliberative Collective Intelligence Framework
- **Date**: 2026-03-14, Research Papers
- **What**: arXiv 2603.11781. 4 reasoning archetypes, 14 epistemic acts, convergent flow. Outperforms unstructured debate.
- **Applies to**: Story ranking
- **How**: Two-agent deliberation: one proposes Top 5 with reasoning, another challenges. Final synthesizer resolves.

### Grok 4.20 Multi-Agent-by-Default
- **Date**: 2026-02-17, Agent Ecosystem
- **What**: 4-agent system: coordinator, fact verifier, technical analyst, creative input. All process in parallel.
- **Applies to**: Synthesis architecture
- **How**: Split into 4 sub-agents: Story Selector (ranks/deduplicates), Narrative Threader (connects stories), Quality Checker (verifies sources), Format Enforcer (length/structure).

### Deterministic Pipeline Orchestration (McKinsey)
- **Date**: 2026-02-27, Best Content
- **What**: State machine transitions outperform autonomous orchestration.
- **Applies to**: Synthesis pipeline
- **How**: Fixed pipeline: Extract → Deduplicate → Score/Rank → Select Top 5 → Assign to Sections → Generate → Evaluate → Fix.

### Self-Healing Router — 93% Fewer LLM Calls
- **Date**: 2026-03-03, Research Papers
- **What**: arXiv 2603.01548. Routing, not reasoning. Cost-weighted tool graph.
- **Applies to**: Model routing in synthesis
- **How**: Fast model for dedup/counting, medium for section drafting, strong model only for Top 5 narrative and evaluation.

## 2.7 Content Quality Research

### AgentDropoutV2 — Cascading Error Prevention
- **Date**: 2026-02-27, Research Papers
- **What**: arXiv 2602.23258. "Rectify-or-reject" between handoffs.
- **Applies to**: Agent report → synthesis handoff
- **How**: Validation step: check URL validity, cross-reference claims, flag single-source findings for verification.

### Search More, Think Less
- **Date**: 2026-03-01, Research Papers
- **What**: arXiv 2602.22675. 70.7% fewer reasoning steps.
- **Applies to**: Synthesis reasoning
- **How**: Gather all evidence first, then make all decisions. Don't interleave reasoning and evidence gathering.

### Longer CoT Negatively Correlated with Accuracy
- **Date**: 2026-03-01, Research Papers
- **What**: r = -0.54 to -0.59. 50% inference cost reduction possible.
- **Applies to**: Synthesis reasoning
- **How**: Limit thinking budget. Structured planning (outline first, then expand) over open-ended reasoning.

### Codified Context Infrastructure
- **Date**: 2026-03-03, Best Content
- **What**: arXiv 2602.20478. Hot-memory constitution + 19 domain-expert agents + cold-memory knowledge base. 283 sessions.
- **Applies to**: Synthesis context
- **How**: Persistent "editorial constitution" + cold-memory store of past newsletter structures and patterns.

### Promptfoo — LLM Red Teaming
- **Date**: 2026-03-11, 2026-03-13 (12.5K stars)
- **What**: Open-source prompt testing. 127 Fortune 500 companies.
- **Applies to**: Synthesis prompt testing
- **How**: Test suite: zero findings, duplicate findings, contradictory findings, extremely long reports, missing agents.

---

# PART 3: SOCIAL MEDIA PIPELINE (65+ Findings)

EIC → writers → critics → art → engagement → posting.

## 3.1 EIC / Topic Selection

### Instruction Compliance Repetition Hack
- **Date**: 2026-03-03, Top 5
- **What**: 21% → 97% compliance by placing critical rules at beginning AND end.
- **Applies to**: EIC prompt
- **How**: Prune EIC prompt to under 50 lines with 5 most critical editorial criteria duplicated at start and end.

### X Platform Grok-Powered Ranking
- **Date**: 2026-02-22, Breaking News
- **What**: X moving to AI-powered content ranking.
- **Applies to**: EIC topic selection
- **How**: Factor in X's Grok algorithm signals when selecting topics for higher organic reach.

### x-research-skill for X/Twitter Research
- **Date**: 2026-02-22, Hot Projects
- **What**: rohunvora/x-research-skill MCP. Decompose questions into targeted X searches.
- **Applies to**: Engagement finder
- **How**: Better engagement target discovery on X via structured research.

## 3.2 Writers — Voice & Authenticity

### humanizer Skill (5.2K stars)
- **Date**: 2026-02-21, Vibe Coding
- **What**: Removes detectable AI writing patterns from text.
- **Applies to**: ALL platform writers
- **How**: Run all drafts through humanizer before posting. Reduces AI detection signals.

### Claude Writing Style Becoming Ubiquitous
- **Date**: 2026-03-03, Reddit (817 upvotes)
- **What**: "I see Claude's writing everywhere." Detectable fingerprint.
- **Applies to**: ALL platform writers
- **How**: Custom system prompts with distinct voice/style parameters. Platform-specific voice tuning essential.

### taste-skill — Fix AI Design Slop (1.2K stars)
- **Date**: 2026-02-25, Hot Projects
- **What**: Single SKILL.md that stops generic AI output. Three tunable parameters.
- **Applies to**: ALL writers
- **How**: Create equivalent "taste-skill" for social writing. Tune per platform voice expectations.

### DPO Fine-Tuning for Writing
- **Date**: 2026-02-13, Skills
- **What**: SFT → generate pairs → rank → DPO.
- **Applies to**: Writer models
- **How**: Collect high/low performing posts, create preference pairs, DPO fine-tune for brand voice.

### Chain-of-Draft for Writers (70-90% Token Reduction)
- **Date**: 2026-02-16, Best Content
- **What**: arXiv 2502.18600. Max 5 words per reasoning step.
- **Applies to**: ALL writers
- **How**: 70-90% cost reduction in writer step with comparable quality.

## 3.3 Critics / Quality Review

### TDD Principles for Content Review
- **Date**: 2026-02-23, 2026-02-24
- **What**: Define tests before implementation.
- **Applies to**: Critic pipeline
- **How**: Define engagement criteria, brand voice checks, platform formatting rules BEFORE writer generates. Critic evaluates against pre-defined tests.

### Blind Validation (Zeroshot Pattern)
- **Date**: 2026-03-03, Vibe Coding
- **What**: Validators assess without seeing implementer reasoning. Prevents rubber-stamp approval.
- **Applies to**: Critics
- **How**: Critic should NOT see writer's reasoning chain — only the final post. More rigorous review.

### PCAS Deterministic Policy Enforcement
- **Date**: 2026-02-21, Research Papers
- **What**: arXiv 2602.16708. 48% → 93% compliance.
- **Applies to**: Critic pipeline
- **How**: Mechanical enforcement of constraints (char limits, forbidden words, required elements) instead of LLM-based "does this follow guidelines?"

### Self-Reflection Security Prompting
- **Date**: 2026-02-28, Skills
- **What**: Databricks. 60-80% improvement from perspective-shifting review.
- **Applies to**: Post-write review
- **How**: "Review this post as a social media expert who has seen thousands of AI posts that flopped. What would you change?"

### Confidence-Aware Self-Consistency — 80% Fewer CoT Tokens
- **Date**: 2026-03-11, Research Papers
- **What**: Single trajectory analysis decides between single-path and multi-path review.
- **Applies to**: Critic efficiency
- **How**: Simple posts get light review, complex/sensitive posts get full multi-pass review. 80% cost reduction.

## 3.4 Art Generation

### Luma Agents: Unified Creative Intelligence
- **Date**: 2026-03-11, Breaking News
- **What**: Unified model trained on audio, video, image, language, spatial reasoning.
- **Applies to**: Art pipeline
- **How**: Replace fragmented image generation with unified creative agent for images, short videos, audio.

### Pencil.dev — Design Canvas with MCP
- **Date**: 2026-02-25, Hot Projects
- **What**: Free design canvas + MCP integration.
- **Applies to**: Visual templates
- **How**: Template-driven visual quality. Agent populates and customizes per-post.

## 3.5 Engagement / Reply Pipeline

### Lightpanda Browser — 11x Faster, 9x Less Memory
- **Date**: 2026-03-13, 2026-03-14 (16.5K stars)
- **What**: Zig headless browser. Puppeteer/Playwright compatible.
- **Applies to**: Engagement finder
- **How**: 11x faster page loads. Monitor more conversations simultaneously. 9x less infrastructure cost.

### Scrapling — 774x Faster Scraping
- **Date**: 2026-02-25, Hot Projects (15.2K stars)
- **What**: Adaptive parser. Learns from website changes. MCP server.
- **Applies to**: Engagement finder
- **How**: Far faster and more reliable social platform monitoring for engagement targets.

### Agent Browser Protocol (ABP)
- **Date**: 2026-03-12, Hot Projects
- **What**: Deterministic browser automation as MCP server.
- **Applies to**: Engagement pipeline
- **How**: Deterministic, reliable social platform navigation. Replaces brittle selectors.

## 3.6 Account Safety

### X Bot Crackdown
- **Date**: 2026-02-26, Breaking News
- **What**: "If a human is not tapping on the screen, account and all associated accounts will be suspended."
- **Applies to**: Posting pipeline
- **How**: Human-in-the-loop interaction required on X. Pure API posting risks bans.

### Two-Stage Jailbreak Defense (Constitutional Classifiers++)
- **Date**: 2026-02-26, Research Papers
- **What**: 0.05% false refusal at ~1% compute overhead.
- **Applies to**: Outgoing posts
- **How**: Screen all posts through lightweight classifier before posting. Catches content that could trigger moderation.

### Multi-Turn Jailbreak Detection (RLM-JB) — 92.5-98% Recall
- **Date**: 2026-02-26, Research Papers
- **What**: Four-stage defense for tool-augmented agents.
- **Applies to**: Reply pipeline
- **How**: Detect when adversarial users try to manipulate engagement agent into harmful replies.

## 3.7 Pipeline Architecture

### Prompt Caching — 78.5% Cost Savings
- **Date**: 2026-02-21, Top 5
- **What**: Static-first prefix. System-prompt-only caching.
- **Applies to**: ALL pipeline stages
- **How**: Structure system prompts as static cached prefixes. Never change between runs. 10x cost reduction.

### Self-Healing Router — 93% Fewer Orchestration Calls
- **Date**: 2026-03-03, Research Papers
- **What**: arXiv 2603.01548. Routing, not reasoning.
- **Applies to**: Pipeline orchestrator
- **How**: Writer fails → router auto-retries with adjusted params. No expensive LLM calls for "what went wrong."

### Deterministic State Machine (McKinsey)
- **Date**: 2026-02-27, Best Content
- **What**: Deterministic transitions outperform autonomous orchestration.
- **Applies to**: Pipeline flow
- **How**: EIC → writer → critic → art → post as deterministic transitions. No step skipping.

### Hook-Driven State Machines
- **Date**: 2026-03-11, Vibe Coding
- **What**: SubagentStart/PreToolUse/SubagentStop as state machine transitions.
- **Applies to**: Pipeline enforcement
- **How**: Each stage must complete and pass quality gates before next activates.

### Rudel: Session Analytics
- **Date**: 2026-03-13, Vibe Coding
- **What**: 1,573 sessions. Error cascades in first 2 minutes predict failure.
- **Applies to**: Pipeline monitoring
- **How**: Track which topics produce worst posts, where failures cascade, what predicts low quality.

### Braintrust Evaluation CI/CD
- **Date**: 2026-02-26, Skills
- **What**: Free-tier. Data + Task + Scorers. Quality gates.
- **Applies to**: Pipeline quality
- **How**: Test cases (sample topics), task (full pipeline run), scorers (engagement, voice, formatting). Block changes that reduce scores.

## 3.8 Content Strategy

### "Chatbait" Pattern Awareness
- **Date**: 2026-03-12, Breaking News
- **What**: AI platforms optimizing for engagement over quality. Audiences are increasingly hostile to this.
- **Applies to**: Content strategy
- **How**: Optimize for genuine value, not engagement bait. Audiences can tell.

### METR Study: AI Adds Most Value on Unfamiliar Tasks
- **Date**: 2026-02-25, Research Papers
- **What**: AI tools make experienced devs 19% slower on familiar tasks. Value comes from reducing context switching on unfamiliar tasks.
- **Applies to**: Pipeline ROI
- **How**: Focus pipeline automation on expanding coverage to new topics/platforms, not speeding up familiar workflows.

### Kleo: $62K MRR Solo Dev LinkedIn Tool
- **Date**: 2026-03-01, Breaking News
- **What**: Claude + Next.js + Vercel stack. AI LinkedIn content.
- **Applies to**: LinkedIn pipeline
- **How**: Reference implementation for LinkedIn content generation. Validates market.

---

# PART 4: INFRASTRUCTURE & MEMORY (86 Findings)

memory.py, orchestrator, cost optimization, security, deployment, monitoring.

## 4.1 Vector Database & Semantic Search

### alibaba/zvec — "The SQLite of Vector Databases"
- **Date**: 2026-02-16, Hot Projects (8K+ QPS)
- **What**: In-process. Billions of vectors in milliseconds. Zero external dependencies.
- **Applies to**: memory.py vector search replacement
- **How**: Replace custom vector search with zvec for in-process hybrid dense/sparse search at 8K+ QPS.

### PageIndex — Vectorless RAG (98.7% Accuracy)
- **Date**: 2026-02-23, 2026-02-28 (19.3K stars)
- **What**: Hierarchical tree indexing + LLM reasoning. No chunking, no vector DB.
- **Applies to**: memory.py retrieval
- **How**: Replace embedding-based retrieval with hierarchical tree approach.

### LEANN — 97% Storage Savings
- **Date**: 2026-02-25 (10.1K stars)
- **What**: On-demand embeddings. Scales to 60M docs on laptop.
- **Applies to**: memory.py storage
- **How**: Compute embeddings on demand instead of storing them. 97% storage reduction.

### OpenViking — L0/L1/L2 Tiered Loading (ByteDance)
- **Date**: 2026-03-01, 2026-03-14 (9.8K stars)
- **What**: Hierarchical filesystem paradigm. Three-tier loading.
- **Applies to**: memory.py architecture
- **How**: L0 (always loaded: identity/prefs), L1 (on demand: recent context), L2 (deep query: historical).

## 4.2 Agent Memory Systems

### EchoVault — MCP Memory Server
- **Date**: 2026-02-25
- **What**: memory_context + memory_search + memory_save. SQLite FTS5. Zero RAM at idle.
- **Applies to**: memory.py as MCP service
- **How**: Expose memory.py as MCP server with standardized tools for any MCP-compatible agent.

### claude-mem — Progressive Disclosure Memory (32.5K stars)
- **Date**: 2026-03-03
- **What**: ChromaDB vector-backed. Progressive disclosure layers context.
- **Applies to**: memory.py context management
- **How**: Return compressed summaries first, expand to full detail on demand. Reduces tokens per query.

### Codified Context Infrastructure
- **Date**: 2026-03-03 (arXiv 2602.20478)
- **What**: Hot-memory constitution + cold-memory knowledge base. 283 sessions, 108K-line codebase.
- **Applies to**: memory.py architecture
- **How**: Explicit hot/cold partitioning with retrieval metrics.

### DeepSeek "Engram" Conditional Memory
- **Date**: 2026-02-12 through 2026-02-28
- **What**: Context-dependent memory retrieval beyond simple vector similarity.
- **Applies to**: memory.py retrieval
- **How**: Conditional retrieval considering full reasoning context, not just query embedding.

### Hindsight — Biomimetic Memory
- **Date**: 2026-03-14 (3.9K stars)
- **What**: World Facts + Experiences + Mental Models. SOTA on LongMemEval.
- **Applies to**: memory.py architecture redesign
- **How**: Three-layer memory: Facts (entities, scores), Experiences (past outcomes), Mental Models (rules of thumb).

## 4.3 Token Cost Reduction

### Prompt Caching — 78.5% Cost Savings
- **Date**: 2026-02-21 (arXiv 2601.06007)
- **What**: System-prompt-only caching optimal. Full-context caching INCREASES latency 8.8%.
- **Applies to**: Orchestrator
- **How**: Static-first prefix, dynamic content last. Target 80%+ cache hit rate.

### Chain-of-Draft — 70-90% Token Reduction
- **Date**: 2026-02-16 (arXiv 2502.18600)
- **Applies to**: ALL research agents
- **How**: Max 5 words per reasoning step.

### Context Mode MCP — 98% Reduction
- **Date**: 2026-03-01
- **Applies to**: Tool output processing
- **How**: Compress agent outputs before orchestrator ingestion.

### rtk — 60-90% CLI Output Compression
- **Date**: 2026-02-27 (1.7K stars)
- **What**: Rust binary between agents and CLI commands.
- **Applies to**: Agents using CLI tools
- **How**: Compress verbose command output before LLM context.

### Progressive MCP Tool Discovery — 32K+ Token Savings
- **Date**: 2026-02-27
- **What**: Load tool schemas on-demand. Context: 49% → 34%.
- **Applies to**: Orchestrator
- **How**: Load only tool metadata at startup, defer full schemas.

### Sub-Agent Compression — 90.2% Performance Improvement
- **Date**: 2026-02-12, 2026-02-27
- **Applies to**: Agent → synthesizer handoff
- **How**: 1-2K token summaries per agent. Full content on demand.

## 4.4 Model Routing

### Sonnet 4.6 at 1/5th Opus Price
- **Date**: 2026-02-17
- **What**: SWE-bench: 79.6% (near Opus 80.8%). $3/$15 vs $5/$25.
- **Applies to**: Research agent routing
- **How**: Sonnet for routine research, Opus only for complex reasoning. 40-80% savings.

### LiteLLM Multi-Provider Routing
- **Date**: 2026-02-27, 2026-02-28
- **What**: 6 strategies, automatic failover, retry policies.
- **Applies to**: Orchestrator
- **How**: Automatic model selection by cost/latency/quality threshold. Failover when APIs unavailable.

### Self-Healing Router — 93% Fewer LLM Calls
- **Date**: 2026-03-03 (arXiv 2603.01548)
- **What**: Routing, not reasoning. 9 calls vs 123.
- **Applies to**: Orchestrator control flow
- **How**: Deterministic graph-based routing. 93% reduction in control-plane LLM calls.

### Perplexity Computer: 19-Model Orchestration
- **Date**: 2026-03-01
- **What**: Decompose goals → route each subtask to optimal model.
- **Applies to**: Research task routing
- **How**: Claude for reasoning, Gemini for research/search, Grok for speed.

### Qwen 3.5 at $0.40/M (10-17x Cheaper)
- **Date**: 2026-02-17
- **What**: 397B MoE, 256K context.
- **Applies to**: Cost-sensitive tasks
- **How**: Bulk extraction and simple summarization at 10-17x cost reduction.

## 4.5 Security Hardening

### OWASP Top 10 for Agentic Applications
- **Date**: 2026-02-17
- **What**: Goal Hijack, Tool Misuse, Memory Poisoning, Supply Chain, Identity/Privilege Abuse.
- **Applies to**: memory.py + orchestrator
- **How**: Memory poisoning defense: validate writes for prompt injection, sanitize data, provenance tracking.

### MCP Security Crisis — 53% Static Credentials, 30+ CVEs
- **Date**: 2026-02-22 through 2026-03-14 (recurring)
- **Applies to**: ALL MCP servers in pipeline
- **How**: OAuth 2.1 + PKCE. Containerize servers. Run mcp-scan regularly.

### SANDWORM_MODE: npm Worm Injecting MCP Servers
- **Date**: 2026-02-26
- **Applies to**: npm dependencies
- **How**: Pin dependencies with lockfiles/checksums. Pre-startup audit of MCP configs.

### PCAS: Deterministic Policy Enforcement
- **Date**: 2026-02-21 (arXiv 2602.16708)
- **What**: 48% → 93% compliance. Zero violations.
- **Applies to**: Orchestrator
- **How**: Deterministic policy enforcement layer intercepting all agent actions before execution.

### AgentBouncr — Deterministic Governance
- **Date**: 2026-02-27
- **What**: JSON policy engine. SHA-256 audit trails.
- **Applies to**: Between orchestrator and external tools
- **How**: Deterministic policy enforcement that prompt injection cannot bypass.

### Pipelock — Agent Firewall (9-Layer Scanner)
- **Date**: 2026-02-28, 2026-03-01
- **What**: DLP, prompt injection, SSRF, MCP tool poisoning. Drop-in proxy.
- **Applies to**: External API calls
- **How**: Deploy as security proxy between orchestrator and all external APIs/MCP servers.

### Varlock — AI-Safe Environment Variables
- **Date**: 2026-03-13 (2.3K stars)
- **What**: Agents read schema but never see raw credentials.
- **Applies to**: Credential management
- **How**: Schema-aware proxies for API access. Agents never see raw secrets.

## 4.6 Orchestration Architecture

### Deterministic State Machines (McKinsey)
- **Date**: 2026-02-27
- **What**: State machine transitions outperform autonomous orchestration.
- **Applies to**: Orchestrator
- **How**: Explicit state machine (discover → collect → synthesize → verify) instead of LLM-directed flow.

### Hook-Driven State Machines
- **Date**: 2026-03-11
- **What**: SubagentStart/PreToolUse/SubagentStop as transitions.
- **Applies to**: Orchestrator
- **How**: Enforce research pipeline phases with hooks. PreToolUse can hard-block violations.

### Pipeline Checkpointing (Microsoft Agent Framework)
- **Date**: 2026-02-21
- **What**: Graph-based orchestration with checkpoints.
- **Applies to**: Orchestrator
- **How**: Resume from last checkpoint on failure instead of restarting entire pipeline.

### TAPE: Adaptive Planning
- **Date**: 2026-02-25 (arXiv 2602.19633)
- **What**: Graph-based multi-plan aggregation + adaptive re-planning.
- **Applies to**: Orchestrator
- **How**: Detect deviations and adjust strategy in real-time.

### AgentSkillOS: Ecosystem-Scale Skill Orchestration
- **Date**: 2026-03-03 (arXiv 2603.02176)
- **What**: Capability tree + DAG-based pipelines for 200-200K skills.
- **Applies to**: Orchestrator
- **How**: Principled skill discovery and composition as agent ecosystem grows.

## 4.7 Monitoring & Observability

### OpenTelemetry Instrumentation
- **Date**: 2026-02-25 (New Relic Agentic Platform)
- **What**: First major observability platform with agent dev stack. OTel integration.
- **Applies to**: Orchestrator
- **How**: OTel traces for every agent invocation, tool call, pipeline stage.

### 12-Metric Reliability Framework
- **Date**: 2026-02-28 (arXiv 2602.16666)
- **What**: Consistency, robustness, predictability, safety. Benchmarks ≠ reliability.
- **Applies to**: ALL agents
- **How**: Track 12 metrics per agent. Data-driven agent selection.

### Rudel Session Analytics
- **Date**: 2026-03-13
- **What**: Error cascades in first 2 minutes predict failure.
- **Applies to**: Orchestrator
- **How**: Tokens per agent, error rates, completion rates, early-failure detection.

## 4.8 Deployment

### Cloudflare Agents — Serverless
- **Date**: 2026-02-22 (3.6K stars)
- **What**: Durable Objects. Hibernate when idle. Zero idle cost.
- **Applies to**: Research agents
- **How**: Deploy as Durable Objects. Pay nothing when idle.

### Docker/Anthropic Sandbox Isolation
- **Date**: 2026-02-16
- **What**: microVM sandboxes. 84% reduction in permission prompts.
- **Applies to**: Research agents
- **How**: Run each agent in isolated sandbox with minimal permissions.

### Alibaba OpenSandbox
- **Date**: 2026-03-03 (4.9K stars)
- **What**: General-purpose sandbox. Docker/K8s. Claude Code + Google ADK + Codex integrations.
- **Applies to**: Agent isolation
- **How**: Production-grade sandboxing for agent workloads.

## 4.9 Knowledge Graphs

### GraphRAG — 30-50% Better Multi-Hop Retrieval
- **Date**: 2026-02-13, Skills
- **What**: Vector similarity + knowledge graph traversal. Microsoft GraphRAG.
- **Applies to**: memory.py
- **How**: Knowledge graph of entities across findings. Graph traversal for relationship-heavy queries.

### GitNexus — Code Knowledge Graph via MCP
- **Date**: 2026-02-24 (2.3K stars), 2026-02-28 (6.7K stars)
- **What**: 7 MCP tools. Function call graphs, dependency trees.
- **Applies to**: memory.py data layer
- **How**: Pre-compute entity relationship graphs and expose via MCP tools.

## 4.10 Error Handling & Recovery

### Agents of Chaos: 16 Real-World Failures
- **Date**: 2026-02-24, Best Content
- **What**: Context compaction = critical failure mode. Agents lose safety boundary awareness.
- **Applies to**: Orchestrator
- **How**: Post-compaction instruction re-injection to prevent safety boundary loss.

### AgentDropoutV2 — Cascading Error Prevention
- **Date**: 2026-02-27 (arXiv 2602.23258)
- **What**: "Rectify-or-reject" between handoffs.
- **Applies to**: Agent → synthesizer
- **How**: Quality gates prevent bad agent output from poisoning synthesis.

### IMMACULATE — Detecting API Provider Cheating
- **Date**: 2026-02-27 (arXiv 2602.22700)
- **What**: Detects model substitution, quantization abuse, token overbilling.
- **Applies to**: Orchestrator
- **How**: Periodic verification that providers are serving correct model quality.

## 4.11 Filesystem Context Patterns

### Spec-Only Pipeline Definition
- **Date**: 2026-02-22 (strongdm/attractor)
- **What**: Zero code, three markdown files. Pipelines as DOT directed graphs.
- **Applies to**: Orchestrator
- **How**: Define pipeline as spec-only directed graph. Auditable, version-controlled.

### AGENTS.md / SKILL.md as Cross-Tool Standard
- **Date**: 2026-02-17 through 2026-03-13
- **What**: Cross-platform agent configuration. 26+ platforms. Curated skills +16.2%.
- **Applies to**: Agent definitions
- **How**: Express agent definitions as standard SKILL.md files for portability.

---

# CROSS-CUTTING THEMES

## Top 10 Most Impactful Findings Across All Categories

| # | Finding | Source | Impact | Applies To |
|---|---------|--------|--------|------------|
| 1 | AGENTS.md repetition hack (21% → 97% compliance) | 2026-03-03 | Critical | ALL prompts |
| 2 | Prompt caching (78.5% cost savings) | 2026-02-21 | High | ALL agents |
| 3 | Sub-agent compression (90.2% performance gain) | 2026-02-27 | High | Agent → synthesis |
| 4 | Self-Healing Router (93% fewer LLM calls) | 2026-03-03 | High | Orchestrator |
| 5 | Chain-of-Draft (70-90% token reduction) | 2026-02-16 | High | ALL agents |
| 6 | Context Mode MCP (98% context reduction) | 2026-03-01 | High | Tool outputs |
| 7 | Deterministic orchestration > autonomous | 2026-02-27 | High | Orchestrator |
| 8 | SMTL — search in parallel, then reason (70.7% fewer steps) | 2026-03-01 | High | Research agents |
| 9 | Lightpanda (11x faster headless browser) | 2026-03-14 | High | Engagement |
| 10 | Hindsight biomimetic memory | 2026-03-14 | High | memory.py |

## Top 10 Tools/Repos for Direct Integration

| # | Tool | Stars | What | Where |
|---|------|-------|------|-------|
| 1 | Lightpanda | 16.5K | 11x faster headless browser | Engagement finder |
| 2 | PageIndex | 19.3K | Vectorless RAG, 98.7% accuracy | memory.py dedup |
| 3 | Scrapling | 15.2K | 774x faster adaptive scraping | Research agents |
| 4 | OpenViking | 9.8K | Tiered context loading | memory.py |
| 5 | EchoVault | — | MCP memory server | memory.py as MCP |
| 6 | Hindsight | 3.9K | Biomimetic agent memory | memory.py |
| 7 | LiteLLM | — | Multi-provider routing | Orchestrator |
| 8 | Promptfoo | 12.5K | Prompt testing/red-teaming | ALL prompts |
| 9 | zvec | 8K+ | In-process vector DB | memory.py |
| 10 | rtk | 1.7K | CLI output compression | Token cost |

## Top 10 Research Papers to Implement

| # | Paper | arXiv | What | Where |
|---|-------|-------|------|-------|
| 1 | IFScale (instruction compliance) | 2026-03-03 | Repetition hack: 21% → 97% | ALL prompts |
| 2 | Don't Break the Cache | 2601.06007 | System-prompt-only caching | ALL agents |
| 3 | Chain-of-Draft | 2502.18600 | 70-90% token reduction | ALL agents |
| 4 | SMTL | 2602.22675 | Search parallel, reason after | Research agents |
| 5 | PCAS | 2602.16708 | Deterministic policy enforcement | Orchestrator |
| 6 | AgentDropoutV2 | 2602.23258 | Cascading error prevention | Synthesis |
| 7 | Self-Healing Router | 2603.01548 | 93% fewer control-plane calls | Orchestrator |
| 8 | RetroAgent | 2026-03-12 | Learning from failures | Self-improvement |
| 9 | DREAM | 2602.18940 | Research agent evaluation | ALL agents |
| 10 | Deliberative Collective Intelligence | 2603.11781 | Multi-agent deliberation | Synthesis |
