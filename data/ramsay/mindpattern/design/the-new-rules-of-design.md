# The New Rules of Design

**How AI Killed the Design Process — And What's Replacing It**

*A documentation of the principles, shifts, and rules emerging from the AI-era transformation of design*

---

## Executive Summary

The traditional design process — discover, diverge, converge, repeat — treated as gospel for two decades, is collapsing under the weight of AI-accelerated engineering. Engineers running seven parallel Claude agents ship features in hours. Designers who block that velocity with months-long discovery cycles get routed around. The role isn't dying — it's splitting into two modes (execution support + short-horizon vision), compressing timelines from years to months, and demanding that designers code, facilitate, and curate rather than gatekeep.

This document captures 13 rules that define the new era, each with a clear before/after comparison, the underlying principle, and what the industry is saying about it.

**Primary Source:** Jenny Wen, Head of Design for Claude/Cowork at Anthropic. Lenny's Podcast, March 1, 2026: *"The design process is dead. Here's what's replacing it."* Previously Director of Design at Figma (FigJam, Slides); designer at Dropbox, Square, Shopify. Also her Hatch Conference Berlin keynote (September 2025): *"Don't Trust the Process."*

---

## Rule 1: The Gospel Process Is Dead

### The Shift

The design sequence taught in every bootcamp and design program — user research → personas → user journeys → wireframes → high-fidelity mocks → handoff → build — assumed designers lead and engineers follow. That assumption broke when engineers got AI agents that ship faster than designers can mock.

### Before → After

| Before | After |
|--------|-------|
| Discover → Diverge → Converge → Diverge → Converge | Prototype → Ship → Learn → Iterate |
| Designers lead the process, engineers implement | Engineers ship continuously, designers guide and polish |
| Process is sacred ("trust the process") | Process is a tool — use what works, discard what doesn't |
| Sequential phases with gates between them | Parallel streams with continuous integration |
| Months of upfront work before any code | Working prototypes in hours or days |

### The Rule

**Don't trust the process. Trust your judgment.** The rigid design sequence is a liability when engineering velocity outpaces it. Use research, divergence, and convergence as tools — not as a religion.

### What Others Are Saying

> *"In a world where anyone can make anything — what matters is your ability to choose and curate what you make."*
> — **Jenny Wen**, Hatch Conference Berlin, September 2025

> *"The process isn't dead — it's redistributing. What changed is the time allocation across design activities."*
> — **Roger Wong**, design analyst, March 2026

> *"AI dramatically lowers the cost of pursuing incorrect directions. Previously, a flawed design could consume months of engineering effort; now, wrong paths consume merely days."*
> — **Simon Willison**, creator of Datasette, Django co-creator

> *"AI cannot replace user research with real users."*
> — **Nielsen Norman Group**, the UX research authority (the counterargument — process still matters for user understanding)

### The Debate

The industry is genuinely split. Jenny Wen acknowledged significant backlash to her Berlin talk: *"People clearly have invested their entire careers in learning, teaching, using this really stable design process."* Roger Wong warns that "ship fast, iterate publicly" worked for Anthropic's greenfield AI products but cites **Sonos and Figma's UI3 failures** as cautionary tales of shipping without sufficient design process.

---

## Rule 2: There Are Now Two Types of Design Work

### The Shift

Design used to be one unified discipline with one process. Now it's stratifying into two fundamentally different modes that require different skills, rhythms, and outputs.

### Before → After

| Before | After |
|--------|-------|
| One design process for all work | Two distinct modes: execution support + vision |
| Designer owns the full lifecycle | Mode 1: Embed with engineers, consult, polish, unblock |
| Vision and execution blend together | Mode 2: Set 3-6 month direction, create prototypes that point the team |
| Same tools, same cadence for everything | Different tools, rhythms, and outputs for each mode |

### The Rule

**Know which mode you're in.** Execution support means pairing with engineers, giving real-time feedback, implementing polish, consulting — not leading. Vision work means creating prototypes and direction that keep autonomous teams aligned — not comprehensive decks.

### Evidence

Jenny Wen on why vision work still matters:

> *"In a world where people can spin off their seven Claudes, make whatever features they want in any direction, you need to point them towards something. If we're all working towards one greater cause, it's much more efficient than just random things."*

The Figma 2026 report confirms this split: **64% of product builders now identify with two or more roles.** The boundary between design, PM, and engineering is dissolving — designers must operate fluidly across modes.

---

## Rule 3: The Time Allocation Has Flipped

### The Shift

The pie chart of a designer's day has fundamentally restructured. The activity that used to dominate — mocking and prototyping in tools like Figma — now takes less than half the time it used to.

### Before → After

| Before | After |
|--------|-------|
| **60-70%** mocking and prototyping | **30-40%** mocking and prototyping |
| **20%** jamming with engineers, consulting | **30-40%** pairing directly with engineers |
| **10%** coordination, meetings | **10-20%** implementing in code (new) |
| 0% writing code | Designers ship PRs |

### The Rule

**If you're spending most of your time in Figma, you're falling behind.** The majority of a designer's value now comes from pairing with engineers, giving real-time feedback on live implementations, and doing last-mile polish in code.

### What Others Are Saying

> *"Designers now spend only 30-40% of time on static deliverables, down from 60-70% previously."*
> — **Geeky Gadgets**, "Design Process Changes in 2026"

> *"60% of Figma files created in the last year were created by non-designers."*
> — **Figma 2026 State of the Designer Report** (906 designers surveyed)

This stat alone tells the story: design tools are no longer the exclusive domain of designers. Everyone is designing now. The designer's value shifts from making the artifact to curating what's good.

---

## Rule 4: Vision Horizons Have Compressed

### The Shift

Long-range design visions assumed a stable technology landscape. When the underlying models change capabilities every few months, a 5-year vision is fiction.

### Before → After

| Before | After |
|--------|-------|
| 2-5-10 year design visions | 3-6 month directional prototypes |
| Beautiful decks with narrative storytelling | Working prototypes that point the team |
| Vision as a document | Vision as a demo |
| "Where will we be in 5 years?" | "What should the next 3 months look like given where models and the market are?" |
| Vision assumes stable technology | Vision accounts for exponential capability change |

### The Rule

**Your vision should be a prototype, not a deck.** If you can't demo it and your timeline is longer than 6 months, it's probably fiction. Create something people can touch and react to.

### What Others Are Saying

> *"Ambitious roadmaps just became realistic ones — but only on 3-6 month windows because the underlying capabilities shift too fast for longer planning."*
> — **Sequoia Capital**, "2026: This is AGI"

METR data shows AI agent capability is doubling every ~7 months. Organizational planning horizons are compressing while AI capability horizons are expanding. The paradox: you can plan less far out, but what you can accomplish in that shorter window is dramatically more.

---

## Rule 5: Designers Write Code Now

### The Shift

The handoff model — designer creates mock, writes spec, throws it over the wall to engineering — assumed designers and engineers speak different languages and use different tools. AI coding tools dissolved that wall.

### Before → After

| Before | After |
|--------|-------|
| Designers mock, engineers build | Designers implement last-mile polish directly in code |
| "Here's the Figma file, good luck" | "I'll pair with you and PR the CSS myself" |
| Technical skills optional for designers | Code literacy is becoming table stakes |
| Prototypes are clickable mockups | Prototypes are real code running real models |
| Design-to-engineering handoff is a formal process | Handoff dissolves into continuous collaboration |

### The Rule

**You don't need to learn React from scratch. You need to know how to use AI coding tools.** The skill isn't writing code — it's communicating design intent to Claude Code or Cursor, recognizing when something's structurally wrong, and articulating what needs to change.

### What Others Are Saying

> *"I ditched every AI design tool for Claude Code. No Figma, no Webflow, no AI wrappers — just sketches, wireframes, and direct implementation."*
> — **Amelia Prasad**, designer, Medium (February 2026)

> *"I built 63 design skills for Claude — and they're free. Research, systems, strategy, UI, interaction design, prototyping and testing, design ops."*
> — **Marie Claire Dean**, designer, Substack

> *"96% of designers learned AI through self-teaching — side projects, peer tips, social media. Formal training is the exception."*
> — **State of AI in Design Report 2025** (Foundation Capital & Designer Fund, ~400 designers surveyed)

Anthropic's own job posting for Product Designer ($260-305K) lists **front-end prototyping expertise (HTML/CSS/JS)** as a preferred qualification. The signal is clear.

**Vercel has gone further** — they don't hire "product designers" at all. The role is **Design Engineer**: *"someone who deeply understands a problem, then designs, builds, and ships a solution autonomously."*

---

## Rule 6: Build Trust Through Speed

### The Shift

Traditional product launches assumed quality requires time. Ship when it's perfect. The AI era inverted this: trust comes from visible, rapid iteration — not from delayed perfection.

### Before → After

| Before | After |
|--------|-------|
| Ship when it's ready | Ship when it's useful, even if imperfect |
| Quality = polish before launch | Quality = speed of iteration after launch |
| "We'll announce when it's perfect" | "Research preview — this is the worst it'll ever be" |
| Trust built through polish and stability | Trust built through responsiveness and visible improvement |
| Feedback collected through formal research | Feedback collected through Twitter, usage data, direct response |
| Brand degrades if you ship something rough | Brand degrades if you ship something rough **and then nothing happens** |

### The Rule

**The only way to lose trust is to ship early and then go silent.** Ship as a research preview, caveat it, respond to feedback publicly, iterate visibly. The promise is: *"We're going to take your feedback, iterate, and make it better."*

### Evidence

Anthropic's build loop:
1. **Prototype** with Claude Code (the prototype becomes the spec)
2. **Release internally** company-wide for dogfooding (not small groups — everyone)
3. **Ship as research preview** with explicit caveats
4. **Iterate publicly** — respond to tweets, fix bugs same-day, ship improvements
5. **Graduate** from preview when the product earns trust through demonstrated improvement

> *"The prototype becomes the spec. The internal usage becomes the research. The feedback becomes the roadmap."*
> — **Aakash Gupta**, on Anthropic's product process

> *"There was no PRD. There's just no way we could have shipped Co-work if we started with static mocks and Figma."*
> — **Boris Cherny**, Head of Claude Code, Anthropic

### The Counter-View

This is not universally accepted. **JetBrains** takes the opposite stance: *"The essential question is not how fast agents can act, but how trustworthy they are when they act. Trust must precede speed."*

**CircleCI's data (28.7M workflows analyzed)** offers a cautionary reality: main branch success rates dropped to **70.8%** — a 5-year low. AI-generated code contains **1.7x more bugs** than human-written code. Speed without validation infrastructure creates fragility, not trust.

The reconciliation: Anthropic's 10-day Co-work build was possible because the product logic was straightforward — **the bulk of engineering was safety engineering** (classifiers, sandboxed VMs, permission models). Speed and trust aren't opposed when the infrastructure exists.

---

## Rule 7: You Can't Mock Non-Deterministic AI

### The Shift

Traditional design assumed deterministic software: given input X, the system always produces output Y. You can mock every state, create a clickable prototype, test every flow. AI broke that assumption completely.

### Before → After

| Before | After |
|--------|-------|
| Mock every state in Figma | You literally cannot mock all states |
| Clickable prototypes simulate the experience | Must use actual models to understand the experience |
| Design for known use cases | Discover use cases by watching people use it |
| Test with scripted scenarios | Test with real users doing real tasks |
| Deterministic: same input → same output | Non-deterministic: same prompt → different responses |
| Edge cases are enumerable | Edge cases are infinite and emergent |

### The Rule

**If your product uses AI, your prototype must use AI.** Static mocks of AI-powered features are fiction. You need the actual model running underneath to understand what you're designing. Use cases emerge during usage, not during planning.

### What Others Are Saying

> *"Retries don't simply repeat the same computation. They generate new outputs. A test that passed yesterday may fail tomorrow without any code changes."*
> — **Guruprasad Rao**, O'Reilly Radar, "AI Is Not a Library"

> *"AI failures are often 'acceptable but wrong' — systems respond, dashboards stay green, but outputs are incomplete or subtly misleading. These erode trust gradually."*
> — **Guruprasad Rao**

The design implication: you must shift from **elimination** of edge cases to **containment** of unexpected behavior. Redefine correctness from "Is this correct?" to "Is this acceptable for this context?"

---

## Rule 8: Figma Isn't Dead, But Its Role Changed

### The Shift

Figma was the center of the design universe — where thinking happened, decisions were made, specs were written, handoffs occurred. Now it's one tool among many, best used for a specific slice of the work.

### Before → After

| Before | After |
|--------|-------|
| Figma is where design happens | Figma is where exploration happens |
| Mock → spec → handoff pipeline | Explore 8-10 directions → pick the best → build in code |
| Figma files are the deliverable | Working code is the deliverable |
| Designers live in Figma all day | Designers use Figma for divergent exploration, code for convergent execution |
| Pixel-perfect handoff documents | Quick exploration of typography, layout, micro-interactions |

### The Rule

**Use Figma for exploration and micro-direction — not for deliverables.** Figma's strength is throwing 8-10 ideas at the wall quickly, exploring different typography and styles on a canvas. That's still valuable. What's not valuable: spending days on pixel-perfect mocks that an engineer will rebuild from scratch with Claude anyway.

### What Others Are Saying

> *"Designers aren't abandoning Figma — they're outgrowing it. Figma is transitioning from an all-purpose tool to a narrower exploration-and-iteration platform."*
> — **Roger Wong**

> *"AI isn't killing design tools. It's killing the boundary between design and engineering."*
> — **Alex Kehr**, on X

> *"Right now, coding tools don't lend themselves to exploration — they're super linear. You invest in one direction and iterate. Figma lets you explore all these different options."*
> — **Jenny Wen**

Meanwhile, **Alex Barashkov** announced plans to *"ban Figma in his design department by end of year, switching to code-driven tools (v0, Claude Code, Cursor)."* The spectrum of opinion is wide — but the consensus is narrowing: Figma's role is shrinking to exploration.

---

## Rule 9: The Gatekeeper Is Dead. The Facilitator Is Born.

### The Shift

Designers used to be the chokepoint through which all product decisions flowed. That model breaks when engineers can ship autonomously at machine speed.

### Before → After

| Before | After |
|--------|-------|
| "Here's the design. Build this." | "What are you building? Let me help make it better." |
| Designer as gatekeeper — nothing ships without approval | Designer as facilitator — help teams ship well |
| All UX responsibility deferred to the designer | Shared ownership of quality across the team |
| Designers block engineers from shipping | Designers unblock engineers and accelerate shipping |
| Formal design review gates | Continuous consulting, whiteboarding, real-time feedback |
| Design as a phase | Design as a continuous activity |

### The Rule

**Your job is not to tell engineers what to build. Your job is to help them build it well.** Equip them with design system components, explain the *why* behind your thinking, point them to research, and then get out of the way. When they ship something rough, jump in and polish it — don't send it back.

### What Others Are Saying

> *"A big part of the design role now is helping engineers and teams execute, not just telling them, here's the design."*
> — **Jenny Wen**

> *"When designers gatekeep, decision-making slows to accommodate the gatekeeper's input on every little detail — and engineers stop trying to think through UI problems."*
> — **Sam Enoka**, designer, Medium

> *"When generative AI tools are used by people with strong product and design sense, we can not only build the product faster than ever, we can figure out the right product to build faster than ever."*
> — **Marty Cagan & Bob Baxley**, Silicon Valley Product Group

**LinkedIn killed their Associate Product Manager program** in December 2025 and replaced it with the **Associate Product Builder** program — a track teaching coding, design, and product management together. Tomer Cohen (LinkedIn CPO): *"Splitting responsibilities across specialists with constant handoffs had slowed product development to a crawl."*

---

## Rule 10: The Confidence Gap Is Real

### The Shift

AI made designers faster. It did not make them more confident. This paradox — 91% faster but only 15% more confident — is the defining tension of design in 2026.

### Before → After

| Before | After |
|--------|-------|
| Slower output, higher confidence in quality | Faster output, lower confidence in quality |
| Validation through craft mastery ("I made this, I know it's good") | Validation crisis ("AI made this, is it good?") |
| Confidence through process completion | Confidence through... what? |
| Designer trusts their output | 40% of designers don't trust AI-generated outputs enough to rely on them |
| Bottleneck: production speed | Bottleneck: discernment and validation |

### The Rule

**Speed is solved. Confidence is the new bottleneck.** The challenge is no longer "how do I produce faster?" — it's "how do I know this is good?" Invest in validation: usability testing, analytics, primary research. Designers who bridge the confidence gap do so through structured validation, not peer discussion.

### The Data (Figma 2026 + UserTesting, combined)

| Metric | Stat |
|--------|------|
| Designers using generative AI tools | 72% |
| Increased AI usage in past year | 98% |
| Say AI makes them faster | 89-91% |
| Say AI improves quality of designs | 91% |
| Feel "much more confident" in quality | **Only 15%** |
| Don't trust AI outputs enough to rely on them | 40% |
| Say the profession has gotten better | 36% |
| Say the profession has gotten worse | 35% |
| Designers leaning into AI who report higher satisfaction | +25% vs those who aren't |
| Figma files created by non-designers | 60% |

> *"When you can generate 30 things in a minute, taste and discernment become more important than ever."*
> — **Andrew Hogan**, Head of Insights, Figma

> *"The problem isn't that AI generates bad outputs — it's that designers don't know how to prove whether outputs are good or bad."*
> — **UserTesting "Defensible Design in the Age of AI" study** (183 designers, March 2026)

Confidence peaks during early exploration and **erodes as stakes rise toward launch**. The confidence gap isn't about AI capability — it's about validation infrastructure.

---

## Rule 11: Three Hiring Archetypes for the AI Era

### The Shift

The traditional design hire — someone strong at the standard design process with a portfolio of polished case studies — is no longer the ideal.

### Before → After

| Before | After |
|--------|-------|
| T-shaped designer (one deep skill, broad base) | Three archetypes: block, deep T, cracked new grad |
| Process mastery valued | Adaptability and resilience valued |
| Portfolio of polished case studies | Portfolio of things you've actually built and shipped |
| Senior experience preferred | "Cracked" new grads with blank slates are the most overlooked hire |
| "Trust the process" mentality | "Roll with it" mentality |

### The Three Archetypes

**1. The Block-Shaped Strong Generalist**
- 80th percentile good at multiple core skills simultaneously — not one deep spike, but a plateau of excellence across design, prototyping, product thinking, and enough engineering to ship
- Matters because the role is stretching into PM and engineering territory simultaneously
- *"In the T-shaped framework, their skill set would look like a block — so many skills that the T is spread out."*

**2. The Deep T-Shaped Specialist**
- Top 10% in their area — could be a designer who is "50% software engineer" or someone with extraordinary visual/icon design ability
- When AI lets anyone produce baseline work, deep specialization becomes the differentiator
- *"Having that deep specialist slant feels like they can really help differentiate the things we're building."*

**3. The "Cracked" New Grad**
- Early career, wise beyond their years, humble, eager to learn
- Their advantage: **no baked-in processes or rituals** — a blank slate that adapts instantly
- *"Given how much the roles are changing, having somebody who almost has a blank slate and is a really quick learner is super valuable."*
- Jenny Wen calls this **the most overlooked hire** in design right now

### What Others Are Saying

The hiring data from Figma 2026 confirms the tension: **56% of organizations seek senior designers vs only 25% seeking juniors** — yet Jenny Wen argues juniors without legacy process attachment may be uniquely suited to this moment.

**73%** of hiring managers see increasing need for AI tool proficiency. **79%** say the same about designing AI products specifically.

> *"When hiring at Anthropic, we look for people who are great communicators, who have excellent EQ, who are kind and compassionate and curious. The things that make us human will become much more important instead of much less important."*
> — **Daniela Amodei**, President, Anthropic (Fortune, February 2026)

**Karri Saarinen (Linear)** hires on craft: *"A lot of times the taste comes from the craft... when you understand your craft really well, you also often have the taste to know what good looks like."* Linear uses **paid work trials** for every role — 50+ hires, 96% retention rate.

---

## Rule 12: The Legibility Framework — Think Like an Internal VC

### The Shift

Designers traditionally worked on well-defined projects with clear briefs. The new skill is spotting proto-ideas — internal prototypes with unexplained energy — and translating them into coherent products.

### Before → After

| Before | After |
|--------|-------|
| Work on defined projects with clear briefs | Scan for illegible ideas with unexplained energy |
| Wait for the brief, then design | Seek out raw prototypes and make them coherent |
| Designer as executor of someone else's vision | Designer as internal VC spotting frontier opportunities |
| Value clear, well-articulated ideas | Pay special attention to ideas people can't quite articulate |

### The Framework

Borrowed from **Evan Tana**, Partner at South Park Commons:

| | Legible Idea | Illegible Idea |
|---|---|---|
| **Legible Founder** | Clear Execution Play — probably already being done | **Frontier Explorer** — the most exciting quadrant |
| **Illegible Founder** | Unlikely to succeed | Hidden Potential — diamonds in the rough |

- **Legible** = well-understood, clear execution path, but predictable and limited impact
- **Illegible** = seems far-fetched or hazy, easily dismissed, but often represents what's coming

### The Rule

**When you see energy around something you don't understand, dig deeper.** The best design opportunities look confusing at first. If researchers or engineers are excited about a prototype but can't articulate why — that's your signal.

### Evidence: How Co-work Was Born

Jenny Wen describes an internal prototype called **"Claude Studio"** — a dense, powerful interface built on an agentic harness with displays showing knowledge, skills, and previews. As a designer, she looked at it and thought: *"I don't know what's going on. I don't really get it."*

But she noticed massive energy from researchers and builders. She dug in. The illegible prototype's concepts — skills framework, plan/to-do displays, context visualization — were extracted and crystallized into Claude Co-work.

> *"People who often gravitate towards these early ideas can't always articulate why, and it's sort of up to you to dive deeper and understand that."*
> — **Jenny Wen**

---

## Rule 13: Low Leverage Is High Leverage

### The Shift

Management wisdom says leaders should only do high-leverage work — delegate everything else. The best leaders do the opposite: they choose specific "low-leverage" tasks that become high-leverage *because* it's them doing it.

### Before → After

| Before | After |
|--------|-------|
| Categorize work into high/low leverage, only do high | Choose specific "low-leverage" tasks that signal care |
| Leaders stay above the details | Leaders who nitpick details build the strongest teams |
| Testing the product is someone else's job | Senior leaders who dogfood obsessively build credibility |
| Pure people management (1:1s, career development, vibes) | Management = direction + people management + hands-on craft |
| Being "above" grunt work | Nothing is below you — and that's the signal |

### The Rule

**The low-leverage stuff is the stuff that often has the most impact — because your reports wouldn't expect you to spend time on it.** A leader who dogfoods the product, repros bugs, files PRs, makes anniversary cards — that leader builds a team that ships with conviction.

### What Others Are Saying

Jenny Wen's approach connects to **Amy Edmondson's Learning Zone framework** (Harvard Business School): the best teams exist at the intersection of **high psychological safety + high standards**.

- Without standards: "comfort zone"
- Without safety: "anxiety zone"
- Both absent: "apathy zone"
- **Both present: "learning zone"** — where the best work happens

> *"The simplest way to hold people accountable is by conveying and inspiring high standards. And also going out of your way to create psychological safety."*
> — **Amy Edmondson**, Harvard Business School

Jenny Wen on her team culture: teammates who feel safe enough to roast each other (and roast her) are teammates who also feel safe enough to give honest design feedback. The roasting is a signal of psychological safety. But it only works **paired with visibly high standards**.

> *"Can you create an environment where your team feels comfortable roasting you, but at the same time they know they have to be doing great work?"*
> — **Jenny Wen**

---

## Bonus: Jenny Wen's 5 Counter-Intuitive Craft Rules

From her Design Leadership Summit 2025 talk, *"Craft is Counter-Intuitive"*:

| Counter-Intuitive Rule | Why It Works |
|---|---|
| **Start in high-fidelity** (skip lo-fi) | AI tools make high-fidelity cheap; lo-fi adds a translation step that wastes time |
| **Flex intuition over process** | Process gives false confidence; trained intuition responds to what's actually happening |
| **Get deeply into details in design crit** | Surface-level feedback produces surface-level work |
| **Change things at the last minute** | Last-minute changes aren't failure — they're responsiveness to new information |
| **Don't shy away from details as a leader** | Leaders in the weeds build credibility and catch problems that distant leaders miss |

---

## The Uncomfortable Middle Ground

Most sources land here: the process isn't dead — it's being **radically compressed and redistributed**.

- Mock-up time drops from 60-70% to 30-40%; freed time goes to engineer pairing and code
- Short-horizon vision (3-6 months) replaces long-range planning (2-5 years)
- Designers become facilitators and curators, not gatekeepers
- Research previews replace polished launches
- The fundamental human skills — taste, judgment, user empathy — matter more than ever
- But the delivery mechanism is completely different

The profession itself is split almost perfectly in thirds on whether things are getting better (36%), worse (35%), or staying the same (29%). The dividing line: **how much an organization invests in craft, leadership attention, and creative autonomy.** Designers at companies that emphasize craft are **twice as likely** to feel good about their work.

> *"In a world of scarcity, we treasure tools. In a world of abundance, we treasure taste."*
> — **Anu Atluru**

> *"The reason most products suck is not because we aren't able to ship fast. It's because we're not shipping the right things."*
> — **Hubert Palan**, Founder/CEO, Productboard

---

## Sources

### Primary Sources
- [The design process is dead — Jenny Wen on Lenny's Podcast](https://www.lennysnewsletter.com/p/the-design-process-is-dead) — Lenny Rachitsky, March 2026
- [Don't Trust the Process — Jenny Wen, Hatch Conference Berlin](https://www.youtube.com/watch?v=4u94juYwLLM) — September 2025
- [Craft is Counter-Intuitive — Jenny Wen, Design Leadership Summit](https://designx.community/talks/jenny-wen-(design-lead-anthropic)-craft-is-counter-intuitive) — 2025
- [Simon Willison's writeup of Jenny Wen's Berlin talk](https://simonwillison.net/2026/Jan/24/dont-trust-the-process/)

### Figma 2026 & Industry Reports
- [State of the Designer 2026 — Figma](https://www.figma.com/reports/state-of-the-designer-2026/) — 906 designers surveyed
- [Figma 2026 Design Report: 5 Things Every UX Designer Should Know](https://uxplaybook.org/articles/figma-2026-design-report-key-findings) — Christopher Nguyen
- [State of AI in Design Report 2025](https://www.stateofaidesign.com/) — Foundation Capital & Designer Fund, ~400 designers
- [Defensible Design in the Age of AI](https://www.usertesting.com/resources/webinars/design-confidence-under-pressure-making-decisions-you-can-defend-age-ai) — UserTesting, 183 designers
- [IDC Design Workforce Study](https://www.figma.com/blog/why-demand-for-designers-is-on-the-rise/) — commissioned by Figma

### Anthropic's Build Philosophy
- [The Way Anthropic Builds Products is Wild](https://aakashgupta.medium.com/the-way-anthropic-builds-products-is-wild-8909a1149fbd) — Aakash Gupta
- [Building Claude Code — Boris Cherny](https://newsletter.pragmaticengineer.com/p/building-claude-code-with-boris-cherny) — Pragmatic Engineer
- [Claude Built Cowork in 10 Days](https://aiagenteconomy.substack.com/p/claude-built-claude-cowork-in-10) — AI Agent Economy
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — Anthropic

### Commentary & Analysis
- [Roger Wong on Jenny Wen's episode](https://rogerwong.me/2026/03/the-design-process-is-dead-jenny-wen-head-of-design-at-claude)
- [Roger Wong on Figma State of the Designer](https://rogerwong.me/2026/03/state-of-the-designer-2026)
- [TeamDay.ai summary](https://www.teamday.ai/ai/jenny-wen-design-process-dead-lennys-podcast)
- [Alan Hou's notes](https://alanhou.org/blog/jenny-wen-design-claude/)

### Designers + Code
- [Why I ditched every AI design tool for Claude Code](https://medium.com/design-bootcamp/why-i-ditched-every-ai-design-tool-for-claude-code-36e0228f28e4) — Amelia Prasad
- [Claude Code for Designers: A Practical Guide](https://nervegna.substack.com/p/claude-code-for-designers-a-practical)
- [I Built 63 Design Skills for Claude](https://marieclairedean.substack.com/p/i-built-63-design-skills-for-claude) — Marie Claire Dean
- [7 AI skills every designer needs in 2026](https://dieproduktmacher.com/insights/7-ai-skills-every-designer-needs-in-2026-and-what-leaders-should-expect)
- [Design Engineering at Vercel](https://vercel.com/blog/design-engineering-at-vercel)

### Hiring & Roles
- [Product Designer, Claude Experiences — Anthropic job posting](https://designproject.io/jobs/jobs/product-designer-claude-experiences-at-anthropic-0r72cz)
- [Anthropic hiring: soft skills matter — Daniela Amodei](https://fortune.com/2026/02/07/anthropic-cofounder-daniela-amodei-humanities-majors-soft-skills-hiring-ai-stem/)
- [Inside Linear: Why Craft and Focus Still Win](https://review.firstround.com/podcast/inside-linear-why-craft-and-focus-still-win-in-product-building/) — Karri Saarinen
- [LinkedIn's Associate Product Builder program](https://drphilippahardman.substack.com/p/the-full-stack-lxd-role-is-coming)
- [NN/g State of UX 2026](https://www.nngroup.com/articles/state-of-ux-2026/)

### Speed vs Quality Debate
- [Speed without fear: Building trust in AI-generated code](https://www.netlify.com/blog/build-fast-how-to-ship-at-ai-speed-without-breaking-things/) — Netlify
- [2025 was the year of speed. 2026 will be the year of quality.](https://www.coderabbit.ai/blog/2025-was-the-year-of-ai-speed-2026-will-be-the-year-of-ai-quality) — CodeRabbit
- [5 key takeaways from 2026 State of Software Delivery](https://circleci.com/blog/five-takeaways-2026-software-delivery-report/) — CircleCI (28.7M workflows)
- [Why Product Judgment Matters More Than Velocity](https://www.productboard.com/blog/product-craft-when-ai-changes-the-stakes/) — Hubert Palan, Productboard
- [Why trust, not speed, defines software leadership](https://www.cio.com/article/4061787/why-trust-not-speed-defines-software-leadership-in-the-ai-era.html) — CIO

### Frameworks
- [Legibility/Illegibility at -1 — Evan Tana](https://www.linkedin.com/pulse/legibility-illegibility-1-evan-tana-gsyhc) — SPC Partner
- [AI Is Not a Library — Nondeterministic Design](https://www.oreilly.com/radar/ai-is-not-a-library-designing-for-nondeterministic-dependencies/) — O'Reilly Radar
- [2026: This is AGI](https://sequoiacap.com/article/2026-this-is-agi/) — Sequoia Capital
- [In Consumer AI, Momentum Is the Moat](https://a16z.com/momentum-as-ai-moat/) — a16z
- [SVPG: Product Design and AI](https://www.svpg.com/product-design-and-ai/) — Marty Cagan & Bob Baxley

### Counter-Views
- [NN/g: AI and UX Getting Started](https://www.nngroup.com/articles/ai-ux-getting-started/) — Nielsen Norman Group
- [Why Trust Leads and Speed Follows](https://blog.jetbrains.com/ai/2025/11/why-trust-leads-and-speed-follows-in-agentic-design/) — JetBrains
- [The AI Product Dilemma: Why Shipping Fast Can Break Trust](https://www.aiceberg.ai/blog/the-ai-product-dilemma-why-shipping-fast-can-break-trust) — Aiceberg
