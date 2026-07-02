# Research: AI-writing tells and human web copy

Date: 2026-07-02
Repo: mindpattern-v3
Scope: Rabbit Hole public site stories, daily site writer, historical backfill
writer harness, and the writer -> critic -> revision gate.

## Bottom line

The harness should not try to prove whether prose was written by AI. That is
the wrong problem. Current detectors are unreliable, biased, and easy to evade.
The useful problem is editorial: reject copy that smells synthetic, unsupported,
generic, promotional, or unreadable on the web.

For Rabbit Hole, "human" should mean:

- specific enough to be falsifiable
- source-grounded enough to be trusted
- plain enough to scan
- opinionated enough to have a point of view
- irregular enough to avoid machine-polished sameness
- constrained enough to avoid invented facts, dates, links, and hype

The current harness already has a good base: hard checks for banned words, em
dashes, invented URLs, raw markdown in public fields, and a Claude critic. The
gap is that many known tells are only prompt instructions today. The next step
is a deterministic copy lint layer plus tests, so every writer provider and
every artifact path gets the same quality floor.

## Research method

Used web search for source discovery, arXiv/Springer/Google/NNG/GOV.UK pages
for primary references, and Agent Reach where available. Agent Reach status:
Twitter via `twitter-cli` worked and surfaced a current practitioner signal
around em dashes; Reddit via OpenCLI failed to start its daemon, so it was not
used as evidence. Agent Reach Exa search was not configured. Jina Reader was
blocked by its anonymous-query reputation gate in this environment, so normal
web fetches were used for source pages.

## Evidence

### 1. AI-detection tools are not a safe quality gate

AI detectors should not be used as the acceptance test for Rabbit Hole copy.
They answer an authorship question and fail in ways that do not map to reader
quality.

- Weber-Wulff et al. tested 12 public AI-text detectors plus Turnitin and
  PlagiarismCheck. Their open-access paper concludes the tools were "neither
  accurate nor reliable," with obfuscation techniques making performance worse:
  https://link.springer.com/article/10.1007/s40979-023-00146-z
- Sadasivan et al. stress-tested watermark, neural, zero-shot, and retrieval
  detectors. Recursive paraphrasing significantly reduced detection rates while
  only slightly degrading quality in many cases:
  https://arxiv.org/abs/2303.11156
- Liang et al. found widely used GPT detectors misclassified non-native English
  writing as AI-generated more often than native-English writing. They also
  showed simple prompting can bypass detectors:
  https://arxiv.org/abs/2304.02819

Harness implication: do not add a third-party "AI detector." Add a house-style
quality linter that flags observable copy defects and source-risk defects.

### 2. Lexical overrepresentation is real

The strongest evidence for "AI-sounding" language is not vibes. It is excess
vocabulary: some words rose sharply after ChatGPT entered common use and are
overrepresented in LLM outputs.

- Kobak et al. studied more than 15 million PubMed abstracts from 2010-2024.
  They found an abrupt increase in certain style words and estimated at least
  13.5% of 2024 biomedical abstracts had been processed with LLMs, reaching
  much higher rates in some subcorpora:
  https://arxiv.org/abs/2406.07016
- Juzek and Ward found increased usage of words such as "delve," "intricate,"
  and "underscore" and identified 21 focal words likely linked to LLM usage:
  https://arxiv.org/abs/2412.11385
- Astarita et al. applied similar analysis to 1 million astronomy articles and
  found statistically significant 2024 increases for ChatGPT-favored words:
  https://arxiv.org/abs/2406.17324
- Yakura et al. found a measurable increase in ChatGPT-preferred words in human
  spoken communication after analyzing large corpora of academic YouTube talks
  and podcasts. Examples include "delve," "comprehend," "boast," "swift," and
  "meticulous":
  https://arxiv.org/abs/2409.01754

Harness implication: keep the banned-word list, but treat it as a living
lexical risk list. Add phrase-level patterns too, because LLM style is often
visible in templates, not just individual words.

### 3. Stylometric differences are broader than word choice

AI writing differs through lexical, grammatical, syntactic, and punctuation
patterns. That means a useful harness should score multiple dimensions rather
than only banning a few tokens.

- Przystalski et al. used stylometric and n-gram features over short samples
  and found LLM text can be separated from human text in defined domains. Their
  explanations pointed to individual overused words and greater grammatical
  standardization:
  https://arxiv.org/abs/2507.00838

Harness implication: add deterministic checks for sameness:

- sentence lengths too uniform
- repeated paragraph openings
- repeated discourse markers
- symmetric contrast templates
- generic summary closers
- all paragraphs landing in the same length band
- every sentence built as polished exposition rather than event, stake, detail,
  counterpoint, consequence

### 4. Em dashes are a perception risk, not proof

Twitter search through Agent Reach surfaced a strong practitioner belief that
em dashes now read as AI-generated. That belief is noisy: many human writers
use em dashes well. But Rabbit Hole already bans em dashes in the voice guide,
so the operational decision is simple.

Harness implication: keep em dashes as a hard fail. The reason is voice and
reader perception, not authorship proof.

### 5. "Humanizing" is useful when it preserves agency and voice

The ethical use case is not detector evasion. It is preserving the author's
voice while improving clarity, structure, and reader fit.

- Hwang et al. interviewed professional writers and surveyed readers on
  human-AI co-writing. Writers cared about authentic voice and reacted
  positively to personalized support, but authenticity was tied to process and
  self-expression, not just whether readers could detect AI assistance:
  https://arxiv.org/abs/2411.13032
- Dhillon et al. ran a co-writing field experiment with varying LLM scaffolding.
  Higher scaffolding improved writing quality and productivity for some users,
  especially non-regular writers and less tech-savvy users, but reduced text
  ownership and satisfaction:
  https://arxiv.org/abs/2402.11723
- Reza et al. reviewed HCI co-writing literature and found writers want
  different levels of AI intervention across planning, translating, reviewing,
  and monitoring. Ownership matters most at different moments depending on the
  writer and domain:
  https://arxiv.org/abs/2504.12488

Harness implication: do not add a "humanizer" pass that blindly rewrites text.
Add an editor pass that preserves:

- the claim
- the source boundaries
- the author's stance
- the useful rough edge
- the reader's path through the story

Practical humanizing use cases:

- Source-grounded web rewriting: convert sourced newsletter excerpts into
  site-native stories without changing the claim or inventing context.
- Voice preservation: keep Tayler's builder judgment, skepticism, and concrete
  operator constraints while cutting machine-polished filler.
- Accessibility and plain-language editing: make dense source material readable
  without flattening it into generic beginner copy.
- Non-native or rough-draft support: improve clarity and rhythm without using
  "AI detector avoidance" as the objective.
- Trust repair: replace vague, mass-produced prose with named actors, numbers,
  source boundaries, uncertainty, and a take a reader can argue with.
- Scan-path design: make the first sentence, first paragraph, dek, and take
  carry enough value for web readers who only read part of the page.
- Reviewer acceleration: give the critic structured lint evidence so the human
  feel is tested consistently instead of depending on vibes.

Non-goals:

- detector evasion
- adversarial paraphrasing
- adding fake typos, fake personal anecdotes, or fake imperfection
- making prose casual at the expense of evidence
- hiding AI involvement by making factual quality worse

### 6. Web readers scan, so web-native writing must frontload value

Rabbit Hole stories are web pages, not essays. Scannability is not optional.

- Nielsen Norman Group's classic web-reading study found 79% of test users
  scanned new pages and only 16% read word by word. Their recommendations:
  highlighted keywords, meaningful subheads, bullets, one idea per paragraph,
  inverted pyramid, and half the word count or less:
  https://www.nngroup.com/articles/how-users-read-on-the-web/
- NNG measured usability improvements from concise, scannable, and objective
  rewrites. The combined version performed 124% better than promotional copy:
  https://www.nngroup.com/articles/how-users-read-on-the-web/
- NNG's F-pattern study says first paragraphs must carry the most important
  information, and subheads, paragraphs, and bullets should start with
  information-carrying words:
  https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content-discovered/
- NNG's reading-time analysis estimates users read about 20% of text on an
  average page:
  https://www.nngroup.com/articles/how-little-do-users-read/

Harness implication: the linter should enforce web shape, not only voice:

- lede must deliver the event
- first sentence should be short enough to scan
- first paragraph must contain the actor and consequence
- body should stay within a target range
- no wrap-up paragraph
- one idea per paragraph
- information-carrying first words

### 7. People-first content requires original value and visible expertise

Google's Search Central guidance is useful because it maps directly to what
generic AI copy lacks: original analysis, clear sourcing, first-hand expertise,
reader satisfaction, and trust.

Reference:
https://developers.google.com/search/docs/fundamentals/creating-helpful-content

Key implications for Rabbit Hole:

- every story needs something beyond "summary of source"
- the take must be an actual judgment, not a balanced non-conclusion
- source trail and claim evidence must be visible
- copy must not be mass-produced content with insufficient attention
- first-hand builder context is valuable when the evidence supports it

### 8. Plain language is the default, not a downgrade

Plain language guidance aligns with Rabbit Hole's desired voice: direct,
specific, active, and designed for the reader's task.

References:

- Digital.gov plain language guide:
  https://digital.gov/guides/plain-language
- GOV.UK tone and style guidance:
  https://www.gov.uk/guidance/style-guide

Harness implication: prefer short familiar words, active voice, named actors,
specific nouns, and direct verbs. Reject inflated professional language unless
it is a proper noun or source term.

## AI-writing tell taxonomy for Rabbit Hole

This taxonomy is not an authorship detector. It is an editorial defect list.

### Lexical tells

Current hard-banned words are right, but should be organized into categories.

Research-linked overrepresentation:

- delve
- intricate
- underscore
- meticulous
- pivotal
- realm
- swift
- comprehend
- boast

Generic AI polish:

- landscape
- nuanced
- robust
- seamless
- comprehensive
- leverage
- utilize
- transformative
- groundbreaking
- cutting-edge
- revolutionary
- innovative
- profound
- illuminate
- testament
- tapestry

Editorial rule: one occurrence of a hard-banned word is a hard fail. Repeated
"soft-risk" words should trigger a revision even if they are not individually
forbidden.

### Phrase and template tells

These are more important than single words.

Hard fail candidates:

- in today's landscape
- ever-evolving
- it is important to note
- it is worth noting
- let's delve
- at the forefront
- not just X, but Y
- no longer just X
- in conclusion
- in summary
- in essence
- this article explores
- this piece examines
- a testament to
- harness the power of
- unlock the potential
- navigating the complexities
- the future of X is here
- game changer
- paradigm shift
- the real kicker
- crucial role
- plays a vital role
- underscores the importance

Revision candidates:

- furthermore
- moreover
- additionally
- ultimately
- notably
- importantly
- interestingly
- significantly
- as such
- when it comes to
- needless to say
- at the end of the day

Editorial rule: hard-fail phrases reject the draft. Revision candidates should
fail when clustered or used as paragraph furniture.

### Punctuation and formatting tells

Hard fail:

- em dash
- raw markdown links in title, dek, take, or why_now
- bold in public fields
- exclamation points in editorial copy
- code-fence residue
- headings that describe the format instead of the story

Revision:

- too many colons in headlines and ledes
- semicolon-heavy exposition
- repeated parentheses
- bullet lists in body unless the evidence really needs enumeration
- more than one "##" subhead

### Structural tells

Hard fail or revise:

- topic-sentence essay structure
- every paragraph similar length
- every sentence similar length
- summary ending
- no concrete actor in first paragraph
- no consequence in first paragraph
- "balanced" take that says nothing
- lede starts with background instead of event
- why_now says "this week" without source-date support
- the story explains the category but not the event
- the body promises more than the evidence supports

### Evidence tells

Hard fail:

- invented URL
- invented date
- invented number
- invented quote
- invented motive
- invented causal mechanism
- vague attribution such as "sources say" when the source list is specific
- references to "evidence pack," "pipeline," "agent," "AI-written," or internal
  artifacts

Revision:

- attribution at the front instead of terminal attribution
- evidence named only in the source trail, not in the body
- no concession when evidence contains a counter-fact
- "experts say" without an expert in the evidence

### Voice tells

Revision or hard fail depending on severity:

- no contractions anywhere in body copy
- over-politeness
- passive voice with unnamed actor
- promotional adjectives where a number or concrete noun should be
- abstract noun stacks
- no lived builder judgment in the take
- generic audience framing such as "businesses must adapt"
- advice without an operator constraint

## Recommended harness design

### Add a shared copy linter

Add a pure module, probably `orchestrator/site_copy_lint.py`.

Proposed public API:

```python
@dataclass(frozen=True)
class CopyLintIssue:
    code: str
    severity: Literal["fail", "revise", "warn"]
    field: str
    excerpt: str
    message: str

def lint_site_story_copy(
    copy: Mapping[str, str],
    *,
    allowed_urls: set[str],
    as_of_date: str,
    source_domains: set[str] = frozenset(),
) -> list[CopyLintIssue]:
    ...
```

The parser, critic, and artifact confidence gate should call this same module.
Do not duplicate regex lists across files.

### Severity model

Fail:

- banned words
- hard-fail phrases
- em dash
- invented URL
- raw markdown in public fields
- source/agent/pipeline machinery mentions
- field missing or too long
- temporal claims not supported by as_of_date or evidence
- final artifact lacks source_refs, claim_evidence, graph_edges, or passed
  redaction

Revise:

- no contractions in body
- sentence over 25 words
- average sentence outside 14-20 words for body
- body outside 150-350 words unless evidence is thin
- repeated paragraph opener
- four same-length sentences in a row
- more than one hedge in story
- generic take
- echo dek
- no actor or active verb in lede
- vague attribution
- adjective inflation

Warn:

- semicolon count above threshold
- parentheses count above threshold
- more than one subhead
- too many transition adverbs
- repeated source domain in body

### Integrate at every ingress point

Use the linter in:

- `parse_writer_output` before accepting agent JSON
- `write_story_with_review` before sending to critic and after revision
- `evaluate_site_story_confidence` before marking publishable
- tests that validate historical backfill artifacts

### Give the critic structured lint evidence

Before the critic call, include a compact lint report in the critic prompt:

```json
{
  "mechanical_lint": [
    {"code": "sentence_too_long", "field": "body_markdown", "excerpt": "..."}
  ]
}
```

The critic should not decide whether hard-fail lint is okay. Hard-fail lint is
not publishable. The critic should decide whether revise-level lint reflects a
real editorial problem or a justified exception.

### Add a regression corpus

Add focused fixtures, not a huge dataset:

- `tests/fixtures/site_copy_lint/good/*.json`
- `tests/fixtures/site_copy_lint/bad/*.json`

Bad fixtures should include one reason each:

- em dash
- banned word
- hard phrase
- invented URL
- unsupported "today"
- machinery mention
- generic take
- echo dek
- raw markdown
- overlong sentence
- no contraction
- summary closer
- repeated paragraph opener
- promotional adjective pile
- vague attribution

### Update prompts

Writer prompt additions:

- write the lede before the background
- make the take falsifiable
- use one concrete operator constraint
- use the source's exact uncertainty when evidence is thin
- no "AI tells" list in the final copy
- preserve useful roughness; do not sand every sentence into corporate polish

Critic prompt additions:

- score robotic smoothness explicitly
- fail "summary of sources" even when factually correct
- fail generic advice
- fail any copy that could fit a competitor's blog with nouns swapped
- prefer shorter copy when evidence is thin

### Add an optional provider-independent critic later

The current critic is Claude-only. If OpenAI subscription usage is desired for
both writer and critic, add a critic provider abstraction after the deterministic
lint layer exists. Do not replace the critic first. The linter gives both
providers the same hard floor.

## Implementation priorities

1. Deterministic lint module and tests.
2. Integrate lint with writer parsing and final artifact gating.
3. Add lint report to critic prompt and update critic tests.
4. Update writer and critic prompt files.
5. Add regression fixtures.
6. Add prompt-contract tests so the operator/goal docs cannot drift.
7. Only then consider OpenAI/Codex critic provider support.

## Acceptance standard

The harness is in good shape when a bad draft cannot survive just because the
critic missed it, and a good draft is allowed to be sharp without being
over-smoothed. Tests should prove both.
