# Shopify-Style AI Design Workflow — Custom Implementation Plan

## What they are actually doing

This workflow is **not** just “use AI to draw UI faster.”

What the Shopify designer is really doing is this:

1. **Thinking in parallel** instead of linearly.
2. **Starting rough and unconstrained** in low-fidelity code.
3. **Converging in a design-system playground** once the form is promising.
4. **Using markdown files as persistent context** so the model can think with continuity.
5. **Using working code as the source of truth**, not static spec pages.
6. **Using the prototype itself to discover product gaps**, edge cases, dead-end buttons, awkward states, and interaction problems.
7. **Replacing handoff docs with forkable, commentable, runnable code artifacts.**

That is the real pattern.

You cannot literally copy Shopify’s internal stack unless you build equivalents for it, but you **can absolutely replicate the method**. This file is the custom plan to do exactly that.

---

## The core thesis

Your new design pipeline should work like this:

- **FigJam / sketchboard** for rough diagrams, flows, notes, and annotated inspiration.
- **Low-fi code sandbox** for primitive exploration with almost no constraints.
- **Design-system playground** for convergence into a realistic product artifact.
- **Markdown context files** for problem framing, requirements, research, constraints, and reusable skills.
- **Multiple AI coding tabs** for independent workstreams.
- **Preview deployments + browser comments** as the new handoff.
- **Short demo videos + shared prompts/skills** as the team learning loop.

If you do this right, Figma stops being the heavy source of truth for end-to-end state documentation. It becomes optional support, not the thing everyone worships like a stale paper map.

---

# 1. Non-negotiable principles from the transcript

## 1.1 Start with roughness on purpose

They did **not** begin inside the polished Shopify design system.

They first used:
- boxy diagrams
- cropped inspiration
- annotated screenshots
- vanilla HTML/CSS/JS

Why this matters:
- rough environments are faster
- the model can remix ideas more freely
- you are not prematurely constrained by component APIs
- you can generate multiple variants quickly
- it feels closer to sketching, but it already runs

**Rule:** Do not start with final components unless the task is a very specific tweak to an existing product surface.

---

## 1.2 Context beats volume

They were not dumping random references into the model.

They were:
- curating screenshots intentionally
- highlighting the exact parts they liked
- cropping to the relevant pattern
- giving problem context in markdown
- feeding the AI real user pain points and constraints

**Rule:** The model should see exactly what matters, not a landfill of screenshots.

---

## 1.3 Work in parallel

They used multiple tabs and multiple active lines of thought:
- one tab refining visuals
- one tab thinking through backend storage
- one tab planning LLM integration
- separate ideation still happening while the model was working

**Rule:** Parallelize non-overlapping threads. Never let two tabs edit the same area at once.

---

## 1.4 Keep scope tiny early

A major detail from the transcript: they deliberately did **not** ask for the full feature all at once.

They asked for:
- the overlay first
- then the close button
- then panel layout changes
- then storage
- then chat/LLM
- then gallery selection
- then export

Why:
- less code slop
- fewer giant file explosions
- easier to verify whether the main surface is correct
- better control over the sequence of interaction design

**Rule:** Build the surface first. Then add one capability at a time.

---

## 1.5 The prototype is a thinking tool, not a deliverable at the end

They kept testing the prototype while designing it.

That surfaced problems such as:
- a dead-end “from gallery” button
- the wrong layout for selecting reference images
- awkward streaming text during generation
- over-large controls and chat input
- empty images being pulled from the DB
- unclear relationship between inputs and outputs

**Rule:** The act of using the prototype is part of design. QA begins during design, not after.

---

## 1.6 Code becomes the collaboration material

The transcript makes this crystal clear:
- PMs can fork the branch
- engineers can fork the branch
- designers keep polishing the same artifact
- everyone works on the same substrate

That is the actual handoff revolution.

**Rule:** Handoff is no longer “translate this spec into code.” Handoff becomes “start from this code artifact and refine it.”

---

# 2. The custom stack that replicates the Shopify method

Below is the practical equivalent stack.

## 2.1 Shopify internal tool → your equivalent

| Shopify concept | What it does | Your equivalent |
|---|---|---|
| FigJam sketchboard | rough thinking, notes, diagrams, inspiration | FigJam, Excalidraw, or Whimsical |
| Mobbin / Pinterest / internal Artifact | inspiration gathering | Mobbin, Pinterest, your own Notion inspiration gallery, internal gallery page |
| Quick | lightweight hosting, share links, DB/storage integrations | Next.js or Vite + Vercel preview deploys + Supabase / Firebase |
| Playground (admin clone + design system) | realistic product prototyping with real components | a sandbox app in your product codebase, Storybook playground, or a dedicated `/playground` route using your real design system |
| Claude Code | agentic coding and planning in repo context | Claude Code, or strongest terminal-based coding agent you trust |
| markdown context files | persistent working memory | `/context/*.md`, `/skills/*.md`, `/research/*.md` |
| AI proxy / quick.AI | model access inside prototype | your own server route or proxy to OpenAI / Anthropic / Gemini |
| internal DB / file storage | store uploaded/generated images | Supabase Storage + Postgres, Firebase, Appwrite, or local mocks first |
| browser comments in preview | async review on prototype | Vercel comments alternative, Liveblocks comments, custom comment layer, or linked review notes |
| Descript + Screen Studio | rapid internal demos and tutorials | Screen Studio, Descript, Loom, Tella, or CleanShot + editor |

### My recommended custom stack for you

Because you are strong in frontend and product building, I would use:

- **Repo:** monorepo or product repo with a dedicated `playground`
- **Low-fi surface:** plain Vite app or static HTML/CSS/JS
- **Design-system surface:** Next.js app route using your actual design system
- **Preview links:** Vercel preview deployments
- **DB + files:** Supabase
- **AI proxy:** server action or API route with provider abstraction
- **Comments:** simplest first = comments in Linear / GitHub PR / Notion tied to preview URL; richer later = Liveblocks or custom annotations
- **Videos:** Screen Studio + Descript
- **Context brain:** markdown files in repo + reusable skills folder

---

# 3. Required workspace structure

Create this exact workspace skeleton.

```txt
ai-design-lab/
├─ apps/
│  ├─ lowfi-prototype/
│  │  ├─ index.html
│  │  ├─ styles.css
│  │  ├─ app.js
│  │  └─ assets/
│  └─ playground/
│     ├─ app/
│     │  ├─ playground/
│     │  │  ├─ page.tsx
│     │  │  └─ components/
│     │  └─ api/
│     │     ├─ generate/route.ts
│     │     ├─ files/route.ts
│     │     └─ favorites/route.ts
│     ├─ components/
│     ├─ lib/
│     └─ styles/
├─ context/
│  ├─ 00_problem.md
│  ├─ 01_user_pains.md
│  ├─ 02_requirements.md
│  ├─ 03_constraints.md
│  ├─ 04_design_direction.md
│  ├─ 05_interaction_model.md
│  ├─ 06_data_model.md
│  ├─ 07_handoff_rules.md
│  └─ 08_review_checklist.md
├─ research/
│  ├─ merchant_pains.md
│  ├─ competitor_notes.md
│  ├─ support_ticket_extracts.md
│  └─ secondary_research_summary.md
├─ inspiration/
│  ├─ raw/
│  ├─ cropped/
│  ├─ annotated/
│  └─ moodboard.figjam-link.md
├─ screenshots/
├─ demos/
├─ mocks/
│  ├─ images/
│  └─ mock-data.json
├─ skills/
│  ├─ flash.md
│  ├─ a11y-pass.md
│  ├─ empty-states-pass.md
│  ├─ ai-state-pass.md
│  ├─ mobile-pass.md
│  ├─ polish-pass.md
│  ├─ edge-case-pass.md
│  ├─ handoff-pass.md
│  └─ component-alignment-pass.md
├─ prompts/
│  ├─ lowfi-bootstrap.md
│  ├─ playground-port.md
│  ├─ db-setup.md
│  ├─ llm-integration.md
│  └─ review-prompts.md
└─ README.md
```

---

# 4. What each file is for

## `context/00_problem.md`
This should answer:
- what problem are we solving
- for whom
- in what product area
- why now
- what task should become easier/faster/clearer

## `context/01_user_pains.md`
Include:
- user pain points
- support-ticket patterns
- research summaries
- quotes if available
- actual friction language

## `context/02_requirements.md`
Split into:
- functional requirements
- non-functional requirements
- prototype requirements
- must-have vs nice-to-have

## `context/03_constraints.md`
Include:
- design-system boundaries
- browser/platform boundaries
- legal/compliance issues
- API limitations
- scope constraints for prototype

## `context/04_design_direction.md`
This is where you define:
- what the UI should feel like
- references to use
- references to avoid
- layout rules
- visual posture
- level of density
- tone of interaction

## `context/05_interaction_model.md`
Describe:
- the main flow
- entry points
- modal/overlay logic
- states
- transitions
- failure states
- loading behavior

## `context/06_data_model.md`
Describe:
- image entities
- prompt entities
- saved/favorite states
- generation records
- export status
- storage assumptions

## `context/07_handoff_rules.md`
Explain:
- how preview links are created
- how naming/branching works
- how comments should be left
- when engineering takes over
- what code is prototype-only vs candidate for production

## `context/08_review_checklist.md`
Checklist for review:
- dead-end buttons
- empty states
- mobile behavior
- accessibility
- loading states
- AI failure states
- visual hierarchy
- keyboard interaction
- copy clarity

---

# 5. The exact project workflow

This is the actual operating sequence.

## Phase 1 — Frame the problem before touching code

### Step 1: Create the problem folder immediately
The transcript showed that this happened right away.

Do this first:
- create the repo folder
- create the context markdown files
- create low-fi and playground app folders
- create inspiration folders

### Step 2: Build a research-backed problem memo
Pull in:
- user pain points
- secondary research
- support evidence
- business goal
- UX goal
- prototype goal

Do **not** start with “make me a cool interface.” That path leads to a haunted carnival of random components.

### Step 3: Open a sketchboard
On the sketchboard, do three things:
- rough boxes for layout ideas
- short notes about what each area does
- screenshots of inspiration with highlighted/cropped regions

This is important: **highlight the exact inspiring part**.

Examples:
- the control panel from one reference
- the gallery sorting behavior from another
- a modal composition from another
- a dark editing canvas from another

That precision is useful for humans **and** for the model.

---

## Phase 2 — Create the low-fidelity code exploration

### Goal
Create a rough but runnable wireframe in primitive code.

### Why low-fi code first
Because it gives you:
- speed
- flexibility
- zero component constraints
- easy variation generation
- a sketch-like environment that still runs

### What to build in low-fi
Only the following:
- main page shell
- one core task flow
- one or two panels
- one main action area
- placeholder states
- fake data

### What **not** to build yet
Do not start with:
- real AI calls
- production routing
- full CRUD
- auth
- analytics
- complex backend logic
- every edge state

### Prompt template for low-fi bootstrap

```md
You are helping me create a rough low-fidelity prototype in plain HTML, CSS, and JavaScript.

Context:
- Read `/context/00_problem.md`
- Read `/context/01_user_pains.md`
- Read `/context/02_requirements.md`
- Read `/context/04_design_direction.md`
- Use the screenshots in `/inspiration/annotated/` as inspiration only, not as exact UI copies.

Goal:
Build a primitive but runnable prototype for the core workflow. Prioritize layout, task flow, and interaction logic over polish.

Rules:
- Keep it lightweight.
- Keep code simple and easy to edit.
- Do not add unnecessary features.
- Do not invent extra product scope.
- Use placeholder/mock data where needed.
- Build only the main surface first.

Deliver:
1. A plan.
2. The minimal file changes.
3. A short explanation of the layout decisions.
```

### What you should do while the model is working
Exactly as in the transcript:
- keep curating inspiration
- keep refining the sketchboard
- create a variant prompt in a second tab
- keep thinking about the problem, not just the pixels

---

## Phase 3 — Diverge with controlled variants

The transcript showed a subtle but powerful move: while one version was being built, they started asking for a second variant.

### Your variant rule
Create variants only when they differ by:
- major layout approach
- information hierarchy
- control placement
- output organization
- interaction strategy

Do **not** generate trivial variants just to feel busy.

### Variant examples
- Variant A: left input panel, center preview, right saved/favorites rail
- Variant B: bottom command bar, center canvas, right multi-select drawer
- Variant C: full-screen modal for choosing reference images instead of cramped side selection

### Important
The low-fi environment is where divergence happens.
The design-system playground is where convergence happens.

---

# 6. Move into the design-system playground

## The trigger to move
Move once the rough structure is good enough that:
- the main workflow makes sense
- the overall composition feels promising
- you can explain the intent to other people
- you are ready to test realism with real components

## What the playground must be
It should be:
- a clone or approximation of your real product shell
- using your actual design system components
- able to generate shareable links
- able to run realistic states

### Minimum viable playground
If you do not have a dedicated playground, build one:

- a `/playground` route in your app
- a fake admin/product shell
- your real design system tokens/components
- toggles for fake states
- local or mock data

### Prompt template for porting low-fi into playground

```md
I want to port my rough prototype into the design-system playground.

Read:
- `/context/00_problem.md`
- `/context/02_requirements.md`
- `/context/04_design_direction.md`
- `/context/05_interaction_model.md`
- the low-fi prototype files in `/apps/lowfi-prototype/`

I am also attaching:
- a screenshot of the current low-fi prototype
- optional inspiration screenshots

Task:
On the [target page/route], add the new interaction surface using the existing design system.

Rules:
- Stay close to the current product shell.
- Use existing components where possible.
- Preserve the rough structure from the low-fi prototype.
- Do not add extra scope.
- Create a scaffold plan first.
- Build only the first meaningful milestone.
```

---

# 7. The exact prompting strategy inside the playground

This part matters a lot.

## 7.1 Describe the target location first
The transcript showed very specific location-based prompting.

Do this:
- name the page
- name the entry point
- name the existing UI element you are anchoring to
- name the desired new surface

Example:

```md
On the Files page, next to the Upload button in the header, add a new Generate button.
When clicked, it should open a full-screen dark overlay with:
- a floating left control panel
- a central preview canvas
- a right-side saved/favorites rail
```

## 7.2 Attach the rough artifact
Give the model:
- a screenshot of the low-fi version
- the low-fi code folder for reference
- the context files

That three-part combo is the sauce:
1. language
2. picture
3. code example

## 7.3 Ask for a plan first
Do not jump straight to implementation on larger steps.

Why:
- lets the model inspect the target area
- surfaces questions early
- reduces messy implementation
- gives you a chance to correct direction before code changes

---

# 8. Scope sequencing — exactly how to build the feature

This is one of the most important parts of the plan.

## Sequence to follow

### Milestone 1: surface only
Build only:
- trigger button
- overlay open/close
- basic page shell inside overlay
- placeholder left / middle / right zones

### Milestone 2: layout and hierarchy
Refine:
- panel placement
- floating vs fixed surfaces
- hierarchy of controls
- spacing and density
- action locations

### Milestone 3: storage
Add:
- mock or real file/image storage
- image records in DB
- file listing on page and overlay

### Milestone 4: generation behavior
Add:
- prompt input
- mock or real generate action
- loading states
- generated outputs
- selection/favorite states

### Milestone 5: gallery/reference import
Add:
- image selection modal
- filtering or choosing existing assets
- selection behavior
- attach reference images to generation context

### Milestone 6: export/save
Add:
- save to gallery
- favorite
- export/download
- metadata or status if useful

### Milestone 7: state refinement
Add:
- empty states
- loading states
- error states
- no-results states
- duplicate prevention
- edge cases

### Milestone 8: responsive pass
Check:
- mobile
- tablet
- awkward widths
- overflow
- rail collapse rules

### Milestone 9: polish pass
Refine:
- hierarchy
- density
- copy
- micro-interactions
- focus states
- timing
- visual tone

---

# 9. Multi-tab operating model

## What separate tabs should do
Open multiple AI coding tabs only when their tasks do not overlap.

Good split:
- Tab A: visual layout and component structure
- Tab B: database/storage setup
- Tab C: AI proxy or mocked generation flow
- Tab D: modal/gallery selector
- Tab E: responsive/mobile pass

Bad split:
- Tab A editing left panel spacing
- Tab B also editing left panel spacing

That is a merge-conflict goblin factory.

## Naming convention for tabs
If your terminal supports renaming, use this:
- `LAYOUT-OVERLAY`
- `DB-IMAGES`
- `LLM-GENERATE`
- `GALLERY-MODAL`
- `RESPONSIVE-PASS`
- `POLISH-PASS`

## Practical rule
Never keep more concurrent workstreams than you can mentally model.
Three is usually sane. Five is where reality starts to smell funny.

---

# 10. Use markdown files as your persistent design brain

The transcript was very clear here: markdown files are not just notes. They are active cognitive infrastructure.

## 10.1 Project context markdowns
These give the AI continuity.

## 10.2 Skills markdowns
These act like reusable lenses or commands.

### Recommended skill files

#### `skills/flash.md`
For rapid critique of a prototype.

Include instructions like:
- identify layout weaknesses
- identify ambiguity in control placement
- identify dead-end actions
- identify missing states
- suggest 3 priority improvements only

#### `skills/a11y-pass.md`
Check:
- contrast
- focus order
- keyboard use
- screen reader labels
- state announcements

#### `skills/empty-states-pass.md`
Check:
- no images yet
- no saved/favorites
- no search/filter results
- no upload history
- no generation results

#### `skills/ai-state-pass.md`
Check:
- generating
- failed generation
- partial result
- retry
- prompt refinement
- multiple outputs
- selection state

#### `skills/mobile-pass.md`
Check:
- panel collapse
- bottom sheet vs modal behavior
- safe tap targets
- scroll traps
- viewport clipping

#### `skills/polish-pass.md`
Check:
- density
- button tone
- awkward rounding
- visual imbalance
- distracting default colors
- title/copy clarity

#### `skills/edge-case-pass.md`
Check:
- dead-end controls
- duplicate actions
- broken references
- empty DB artifacts
- upload failure
- stale selected state

---

# 11. Backend strategy — how to replicate the “quick DB + AI proxy” move

The transcript showed a very specific sequence:
1. get the visual shell working first
2. add storage
3. add LLM integration
4. mock if real integration will slow the demo

That is the right order.

## 11.1 Storage first
Why storage first:
- it makes the prototype feel real quickly
- it grounds the generation workflow in persistent artifacts
- it lets you test real flows like upload, select, save, re-open

### Minimum storage model

```ts
ImageAsset {
  id: string
  url: string
  type: 'uploaded' | 'generated'
  prompt?: string
  favorite: boolean
  createdAt: string
  source?: string
}
```

### What to implement first
- upload image
- list images
- show images in overlay/gallery
- mark favorite/save

## 11.2 LLM or image-gen integration second
You have two options:

### Option A — mock first
Use this when:
- demo speed matters
- provider setup is annoying
- you are exploring interaction design, not model quality

### Option B — real integration
Use this when:
- you need to feel the conversational flow
- prompt shaping is part of the design
- model latency impacts the UX

### Smart compromise
Use a real text model for prompt/refinement behavior, but use mocked image outputs initially.
That gets you 80% of the interaction truth without drowning in infra soup.

---

# 12. Designing AI-native interactions correctly

The transcript exposed several important design lessons for AI products.

## 12.1 Static design is weak for AI-first flows
Why:
- conversational states are open-ended
- response timing matters
- generation feedback matters
- the relationship between input and output is dynamic

This is why code beats static frames for AI-first work.

## 12.2 Prefer visible progress states over weird text streaming
The designer explicitly disliked streaming text for image generation feedback.

Use instead:
- skeleton cards
- pulsating placeholders
- progress chips
- “Generating 4 concepts…” states
- selectable result cards after completion

## 12.3 Separate input, preview, and saved output clearly
A useful layout pattern from the transcript is:
- **left:** prompt + controls
- **middle:** generation result / preview canvas
- **right:** saved/favorites/export area

That separation is strong because it mirrors user intent:
- instruct
- inspect
- keep/discard/export

## 12.4 Use the right surface for picking reference images
The transcript discovered that a cramped sidebar selection UI was the wrong choice.

Correct pattern:
- open a modal or larger gallery surface
- show actual image thumbnails clearly
- allow simple multi-select
- confirm selection back into main flow

That insight emerged by using the prototype, not by guessing from afar like a decorative oracle.

---

# 13. How to critique and refine sections one at a time

Once the first working version exists, do section-based refinement.

## The right loop
For each section:
1. use it
2. notice friction
3. articulate the problem precisely
4. attach a screenshot if useful
5. request a targeted fix
6. re-test

## Good prompt pattern

```md
The current overlay is close, but the left panel feels too heavy.

Problems:
- padding is too large
- the chat input is oversized
- all-caps section headers feel noisy
- control grouping is unclear

Task:
Refine the left panel only.
Keep the overall layout intact.
Do not touch the center preview or right rail.
Make a plan first, then implement.
```

## Bad prompt pattern

```md
Make this whole thing better and more polished and smarter and cleaner.
```

That is not direction. That is how you summon generic AI goo.

---

# 14. Review methodology — how the prototype replaces static specs

## Old model
The transcript described the old model clearly:
- many Figma pages
- every breakpoint documented
- every state manually maintained
- before/after pages
- stale references everywhere
- people accidentally using the wrong screen

## New model
The new model is:
- one living prototype branch
- preview link as the review artifact
- comments directly on the working thing
- before/after = separate branches or preview links
- source of truth updated by changing the actual artifact

## What this means for you
Your prototype becomes:
- demo artifact
- review artifact
- alignment artifact
- early QA artifact
- partial handoff artifact

That is a huge compression of work.

---

# 15. Sharing and handoff process

This is how to operationalize the share loop.

## 15.1 Preview deployment rules
Every meaningful prototype state should get:
- a branch
- a readable branch name
- a preview URL
- a short description of what changed

### Branch naming
Use:
- `poc/studio-generator-v1`
- `poc/studio-generator-layout-b`
- `poc/studio-generator-gallery-modal`
- `poc/studio-generator-mobile-pass`

## 15.2 What to send to stakeholders
Send:
- preview URL
- one-sentence purpose
- 3–5 things to test
- any known rough edges

### Example review note

```md
Prototype review: Studio Generator POC

Preview focus:
- opening and closing the overlay
- generating concepts
- selecting favorites
- importing from gallery
- overall layout clarity

Known rough edges:
- export is placeholder
- image-gen is partially mocked
- mobile pass not complete yet
```

## 15.3 PM collaboration
PM should be able to:
- click the preview
- leave comments
- fork or branch if they are technical enough
- suggest copy and workflow changes using the same artifact

## 15.4 Engineering collaboration
Engineering should receive:
- the branch
- the preview
- notes on what is real vs mocked
- notes on what can survive into production
- notes on known slop areas

### Very important
Do not pretend prototype code is clean production code.
The transcript explicitly acknowledged there will still be slop:
- i18n cleanup
- implementation hardening
- production standards
- architecture tightening

So the handoff is **accelerated**, not magically complete.

---

# 16. Definition of done for prototype maturity

A prototype is mature enough for serious review when:

- the core task flow works end to end
- the primary actions are not dead ends
- the major states are represented
- the layout and hierarchy communicate intent clearly
- the prototype can be shared via a stable link
- stakeholders can comment without installing local tooling
- the artifact is specific enough that engineering can meaningfully refine from it

A prototype is **not** mature just because it looks shiny.

---

# 17. Daily and weekly habits to replicate the culture

The transcript revealed that this is not just a tool workflow. It is a culture workflow.

## Daily habit 1 — inspiration intake
Spend 10 minutes most mornings doing one of:
- Mobbin browsing
- Pinterest board curation
- internal gallery review
- saved bookmarks review
- app teardown screenshots

### Rule
Always save inspiration into categorized buckets.
Do not rely on memory.
Creative memory is a trickster goblin.

## Daily habit 2 — context capture
As project knowledge grows, keep updating:
- context markdowns
- research extracts
- skills markdowns
- issue log / friction notes

## Weekly habit 1 — short demo recording
Record one short demo of:
- what changed
- what you learned
- what still feels wrong
- what patterns seem promising

## Weekly habit 2 — share prompts and skills
If a prompt or skill worked, save it.
If it worked twice, template it.
If three people need it, publish it internally.

---

# 18. Build your own mini “AI hub”

The transcript described a company-level AI learning hub. You should create a smaller version.

## What your AI hub should contain
Create a Notion space, repo folder, or internal doc with:
- setup guide
- project template
- prompt library
- reusable skills markdowns
- MCP/server connection docs
- example prototype repos
- video walkthroughs
- review checklist
- mistakes and anti-patterns

## Minimum sections

### `Getting started`
- clone template repo
- install dependencies
- run low-fi app
- run playground app
- create new project branch

### `Prompt library`
- low-fi bootstrap
- design-system port
- storage setup
- AI integration
- polish pass
- accessibility pass
- mobile pass
- edge-case pass

### `Patterns`
- overlay layouts
- right rail patterns
- gallery modal patterns
- AI generating states
- favorite/save/export interactions

### `Anti-patterns`
- too much scope too early
- multiple tabs editing same component
- using generic inspiration without highlighting specifics
- staying in Figma too long for AI-native flows
- shipping preview links without test notes

---

# 19. Video-sharing workflow

The transcript used Screen Studio + Descript as the sharing loop.

## Your exact process

### Step 1: Record quickly
Use Screen Studio or Loom to record:
- what changed
- what to pay attention to
- where the rough edges are

Do not try to be cinematic unless the audience is large.

### Step 2: Clean lightly
Use Descript or equivalent to:
- remove obvious filler words
- trim pauses
- cut false starts
- tighten to 1–3 minutes

### Step 3: Share with purpose
Every video should answer:
- what is this
- what changed
- what feedback do I need
- what is still fake or unfinished

### Rule
Do not over-polish internal learning videos.
Use enough polish to communicate clearly, not enough to delay the team for theatrical reasons.

---

# 20. The exact prompt library you should start with

## 20.1 Prompt: bootstrap project understanding

```md
Read all markdown files under `/context` and `/research`.
Summarize:
1. the user problem
2. the product goal
3. the prototype scope
4. the top design constraints
5. the unknowns we still need to resolve

Then propose the smallest prototype milestone that would let us start learning quickly.
```

## 20.2 Prompt: create the low-fi wireframe

```md
Use plain HTML/CSS/JS to create a low-fidelity but runnable wireframe for the main workflow.
Prioritize task flow, layout, and state clarity over polish.
Do not add production complexity.
Build only the first milestone.
```

## 20.3 Prompt: generate a second layout variant

```md
Create Variant B of this prototype.
Keep the core workflow the same, but change the layout and control hierarchy substantially enough to compare approaches.
Do not add new product scope.
```

## 20.4 Prompt: port into design-system playground

```md
Using the low-fi prototype as inspiration, recreate the experience inside the design-system playground on the target route.
Use existing components where possible.
Create a scaffold plan first.
```

## 20.5 Prompt: storage setup

```md
Set up the smallest possible storage layer for uploaded and generated images.
We need to:
- upload images
- list them
- show them in the overlay
- save/favorite them

Use mock data where useful, but structure it so we can swap in the real backend cleanly.
Create a plan first.
```

## 20.6 Prompt: mock generation flow

```md
Implement a mocked generation flow.
When the user clicks Generate:
- show 4 pulsating skeleton cards
- then replace them with mock generated images
- allow selecting favorites
- do not stream placeholder text during generation
```

## 20.7 Prompt: gallery modal fix

```md
The current gallery selection UI is too cramped and unclear.
Replace it with a modal that lets the user browse and select existing images more comfortably.
Focus only on this flow.
```

## 20.8 Prompt: polish pass

```md
Review this prototype for visual and interaction polish.
Focus on:
- density
- overly large controls
- awkward rounding
- hierarchy problems
- noisy headings
- distracting colors

Return the 5 highest-value refinements and then implement only those.
```

## 20.9 Prompt: mobile pass

```md
Test the prototype at narrow widths and improve the responsive behavior.
Focus on:
- panel stacking/collapse
- overflow
- button sizing
- modal behavior
- scroll traps

Do not change desktop behavior unless necessary.
```

## 20.10 Prompt: edge-case pass

```md
Use the prototype like a real user and identify dead ends, broken assumptions, empty states, and state inconsistencies.
List the issues in priority order and fix the top 3.
```

---

# 21. The exact behavior rules for the AI coding assistant

Add these as explicit instructions in your project README or context files.

## Rules
- Start with a plan for any non-trivial change.
- Keep scope minimal.
- Never edit unrelated areas.
- Prefer the smallest complete milestone.
- Mock where real integration would slow design learning.
- Explain assumptions.
- Do not create unnecessary files.
- Do not invent extra features.
- Reuse existing components where appropriate.
- Preserve the existing product shell unless told otherwise.

These rules are crucial. Without them, the model will happily wander off and build a conceptual amusement park you never asked for.

---

# 22. When Figma still matters

This workflow does **not** mean Figma dies completely.

Use Figma when:
- you need fast compositing of screenshots
- you need to collage interaction ideas from multiple references
- you need to annotate visuals for a model
- you need to communicate a static concept before code exists
- you need stakeholder storytelling visuals

But for AI-native interaction design and multi-step flows, the transcript was dead right:
**code becomes the better medium sooner than most design teams expect.**

---

# 23. 30-day rollout plan to adopt this workflow

## Week 1 — Build the infrastructure

### Goal
Create the environment, not the masterpiece.

### Tasks
- create the repo structure above
- create a low-fi prototype app
- create a design-system playground route
- set up preview deploys
- set up Supabase or local mock backend
- create starter context files
- create starter skill markdowns
- create branch naming conventions
- create review template

### Output
A reusable template project.

---

## Week 2 — Run one full pilot project

### Goal
Use the workflow on a real feature.

### Tasks
- collect research and pains into markdown
- create annotated moodboard
- sketch box diagrams
- build low-fi prototype
- generate 1–2 meaningful variants
- port best direction into playground
- add mock storage/generation
- share first preview link

### Output
One end-to-end prototype reviewable in browser.

---

## Week 3 — Add collaboration and handoff

### Goal
Make the artifact forkable and reviewable by others.

### Tasks
- get PM feedback on preview link
- get engineer feedback on branch viability
- define what code is throwaway vs production-candidate
- add comment workflow
- record short video walkthrough
- create first internal case study of time saved and issues found early

### Output
A repeatable collaboration loop.

---

## Week 4 — Productize the workflow

### Goal
Turn your personal method into team infrastructure.

### Tasks
- publish your AI hub
- add templates and prompts
- publish demo video
- document anti-patterns
- create project kickoff checklist
- create prototype review checklist
- create engineering-ready handoff checklist

### Output
A system, not a one-off trick.

---

# 24. The exact checklist to run every project

## Project kickoff checklist
- [ ] Create project folder/repo structure
- [ ] Create context markdowns
- [ ] Add research and pains
- [ ] Create moodboard with highlighted inspiration
- [ ] Draw boxy flow diagrams
- [ ] Decide low-fi milestone
- [ ] Start low-fi prototype

## Low-fi prototype checklist
- [ ] One main workflow exists
- [ ] Layout hierarchy is understandable
- [ ] At least one variant explored if needed
- [ ] Scope is still small
- [ ] Prototype is runnable

## Playground port checklist
- [ ] Target page and entry point are clear
- [ ] Design-system components are used where sensible
- [ ] Main surface exists
- [ ] Overlay/modal open-close works
- [ ] Core zones/panels are mapped

## Interaction checklist
- [ ] No dead-end primary buttons
- [ ] Loading states exist
- [ ] Empty states exist
- [ ] Error behavior at least mocked
- [ ] Selection/favorite/save logic is understandable
- [ ] Input/output relationship is clear

## Review checklist
- [ ] Preview URL created
- [ ] Review note written
- [ ] Known rough edges listed
- [ ] Stakeholders know what to test
- [ ] Branch name is readable

## Handoff checklist
- [ ] Engineering knows what is mocked
- [ ] Engineering knows what is reusable
- [ ] Prototype has enough specificity to refine from
- [ ] Comments and feedback are attached to the runnable artifact

---

# 25. What success looks like

You know this workflow is working when:

- what used to take days now takes hours
- what used to require many Figma pages is handled in one living branch
- PMs and engineers review the same working artifact
- you discover dead ends during design instead of during QA
- you spend more time refining quality and less time maintaining stale specs
- the model has persistent context across the whole project
- your prototype is realistic enough that collaboration starts from code, not translation

That is the real win.

---

# 26. Final operating model in one sentence

**Rough ideas in annotated boards → fast low-fi code exploration → convergence in a design-system playground → storage and AI stitched in incrementally → preview link as source of truth → branch/fork/comment as the new handoff.**

That is the process.

---

# 27. My direct recommendation for you

If you want to mirror this as closely as possible, start with this stack immediately:

- `FigJam` for boxy diagram thinking + annotated inspiration
- `Mobbin + Pinterest + your own saved references` for intake
- `Claude Code` in a repo with strong markdown context files
- `Vite low-fi app` for unconstrained exploration
- `Next.js playground route` using your real design system for convergence
- `Supabase` for image/file storage and lightweight DB state
- `API route` for mocked or real AI generation
- `Vercel preview links` for share/review
- `Screen Studio + Descript` for demos and teaching
- `skills/*.md` as your reusable design/QA lenses

That will get you very close to the Shopify method without needing Shopify’s internal universe.

---

# 28. The one mistake not to make

Do **not** skip the rough low-fi stage and jump straight to polished design-system work unless the task is narrowly scoped.

That rough stage is where the freedom lives.
That freedom is why this workflow moves so fast.
If you start too polished, you drag the old world back in through the side door wearing a component library as a fake mustache.

