# Rabbit Hole Writer's Rules

The rules every public site story is written and judged against. Distilled from
NN/g eyetracking research, readability science (American Press Institute,
Flesch), GOV.UK content design, AP/Reuters lede and attribution discipline,
Axios Smart Brevity, the Economist style guide, Bloomberg's nut-graf practice,
and the craft of Stratechery, Money Stuff, and The Information. The voice guide
(voice.md) governs tone; this governs structure and craft. Sources and research
notes live in `docs/handoff/2026-07-02-writing-research.md`.

## The structure (200-350 words total)

- **Headline**: 6-10 words, 60 characters target (90 hard max). Active verb,
  strongest words first, states the event. Understandable with zero context.
  The story must deliver exactly what it promises. Never a tease, never
  "Introducing", "New", "A look at", "Why".
- **Dek**: one sentence, 160 characters max, first 120 must stand alone. Adds
  NEW information the headline doesn't have: the consequence, the twist, or
  the why-now. Never restates the headline.
- **Lede** (first sentence of the body): 30 words max, the single most
  interesting thing, main active verb inside the first 7 words. Attribution
  at the end of the sentence, never the start.
- **Why it matters**: 1-2 sentences right after the lede. What's at stake, for
  whom, with a number when one exists.
- **Details**: the middle of the body. One idea per paragraph, 1-3 sentences
  each. Specifics carry inline attribution ("per the CVE advisory"). If the
  evidence contains a counter-fact, give it one sentence ("Yes, but...").
- **Take**: one falsifiable claim someone could bet against, stated plainly,
  that reframes the event. Plus, when the evidence supports it, a concrete
  thing to watch next. Never "time will tell", never a balanced non-conclusion.
- **Why now**: one sentence on timing, specific to this week's evidence.
- End when the information ends. No wrap-up, no summary paragraph.

## Sentences and words

- Sentences average 14-20 words. Hard cap 25. Vary the rhythm: mix short
  fragments with longer sentences; never four same-length sentences in a row.
- Grade 10-12 reading ceiling. Domain terms are fine, syntactic complexity is
  not. Verbs over noun phrases ("ships" not "is making available").
- Numbers over adjectives. "$550M round" beats "a huge round". Every
  "significant / notable / major" is a fact you failed to find.
- Active voice with named actors. "Anthropic shipped X", never "X was
  announced".
- Draft, then cut. Readers read about 20% of a page; the word budget is real.

## Time

- Anchor time to the evidence pack's as_of_date. Never write "this week",
  "today", "just", or "now ships" unless the evidence itself dates the event.
  Use the absolute date ("on June 28") or drop the timing.
- why_now references the as_of_date's coverage, not invented recency.

## Evidence and honesty

- Every claim traces to the evidence pack. No new facts, numbers, quotes, or
  URLs. Fabrication kills the story.
- Attribution is specific and terminal: "..., per the S-1." Never "sources
  suggest" floating vaguely.
- Say what you don't know when it matters ("the advisory doesn't say whether
  the fix is backported"). Stated uncertainty is a credibility feature.
- Never mention the machinery: "evidence pack", "pipeline", "the pack",
  "as_of_date", agents, or these rules must not appear in copy. Attribute
  gaps to the SOURCE ("GitHub's post doesn't list the six settings"), never
  to internal artifacts. No outlet cites its own research file.
- The headline must be verifiable against the body.

## Banned moves (beyond the voice guide's banned words)

- Didactic imperatives opening sentences: Consider, Note, Imagine, Remember.
- Qualifier pile-ups: "arguably", "potentially", "somewhat" stacked; more than
  one hedge per story.
- Curiosity-gap teases: "you won't believe", withholding the noun the headline
  is about.
- Symmetric contrast slop: "It's not just X, it's Y".
- Echo furniture: a dek or subhead that restates instead of advancing.
- Marketese: boastful adjectives, hype framing, exclamation points.
- Wrap-up closers: "In conclusion", restating the top, "exciting times ahead".

## The one test

Read it aloud. If it sounds like a press release or a textbook, rewrite it.
If a smart reader couldn't repeat the take at dinner, sharpen it.
