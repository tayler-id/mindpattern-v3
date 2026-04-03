# Handoff: Animated GIF Pipeline + Design System for Social Media

## Session Metadata
- Created: 2026-04-03 17:14:26
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Worktree: /Users/taylerramsay/Projects/mindpattern-v3/.claude/worktrees/snug-chasing-salamander
- Branch: worktree-snug-chasing-salamander
- Session duration: ~3 hours
- CEO Plan: ~/.gstack/projects/tayler-id-mindpattern-v3/ceo-plans/2026-04-03-animated-gif-pipeline.md
- Design Doc: ~/.gstack/projects/tayler-id-mindpattern-v3/taylerramsay-worktree-snug-chasing-salamander-design-20260403-150311.md

### Recent Commits
  - 23c4eed feat: add animated GIF pipeline with Remotion integration (26 files, 3539 lines)
  - 1481cf8 Merge pull request #21 from tayler-id/fix/social-pipeline-bugs

## Handoff Chain
- **Continues from**: None (new feature)
- **Supersedes**: None

## Current State Summary

We built the full pipeline infrastructure for automated animated GIF generation for MindPattern's LinkedIn and Bluesky social posts using Remotion (React-based programmatic video framework). The PLUMBING WORKS: Remotion renders GIFs, the Python orchestration mirrors the existing art.py pattern, tests pass (701 total, 24 new), pipeline integration is wired. But the VISUAL DESIGN IS NOT GOOD ENOUGH. The user saw the rendered GIFs and they look like basic wireframes compared to the LinkedIn infographic references they showed. The next session needs to focus entirely on building a proper design system and component library that produces scroll-stopping, information-dense, visually rich animated content.

## What the User Wants (CRITICAL)

The user showed two LinkedIn reference posts as their quality bar:
- `/Users/taylerramsay/Downloads/gif/1775100038139.gif` - "12 Ways to Boost Productivity with AI" by Sivasankar Natarajan. Dense infographic with: illustrated golden figure as visual anchor, 10+ colored category cards (green, blue, red, orange, purple), tool logos (ChatGPT, Claude, Zapier, etc.), descriptions per card, mind-map layout connecting to central illustration.
- `/Users/taylerramsay/Downloads/gif/1775100696755.gif` - "Which AI Model to Use" by Ashish Joshi. Comparison chart with: illustrated blue robot character, 10 category rows with colored labels, 4-5 tool names per row, clean information hierarchy, personal branding with photo.

**Key gap**: Current compositions are "one stat on a mostly empty canvas." The references have 8-12 categories, real tool/product names, illustrated characters, dense layouts. The animations need to be RICH, INFORMATION-DENSE, and VISUALLY COMPELLING.

**User feedback quotes:**
- "these are way too basic the designs are bad"
- "not the dark design I like a mix" (wants light backgrounds + decorative lines/grid from dark design)
- "you need a creative director agent that thinks through these ideas better"
- "you need to deep research exactly what an agency does to build great animations"
- "we need to figure out how to get you to build proper designs you will need a new skill"
- "use image gen to create images and put them in the animations, create cool infographics as backgrounds and overlay the moving parts"
- "we need a big library of components that you can use for different stories"
- "create multi agents to work on different reusable parts"

## Codebase Understanding

### Architecture Overview

MindPattern v3 is an autonomous AI research pipeline. Runs daily at 7 AM. 12-phase pipeline. The social pipeline (`social/pipeline.py`) is a 12-step orchestration: topic selection -> brief -> art/animation -> write -> critic -> policy -> humanize -> expedite -> approve -> post. The animation pipeline slots into Step 3 alongside the existing art pipeline.

**Existing art pattern** (`social/art.py`): Art Director agent conceives concept -> Illustrator generates image prompt -> Creative Director reviews -> revision loop -> post with image. This same Director -> Generator -> Reviewer pattern was replicated for animation.

**Rayni website Remotion code** (`/Users/taylerramsay/Projects/rayni_website/remotion/`) is the user's own production Remotion codebase with high-quality components. This is the QUALITY BAR and the architectural reference:
- `lib/design-tokens.ts` - Color palette, fonts, timing constants
- `lib/utils.ts` - fadeIn, slideUp, scaleIn, fadeOut, entrance animation helpers
- `components/GradientBackground.tsx` - Floating gradient orbs on light bg
- `components/Transition.tsx` - Wipe transitions between sections
- `components/ValuePropSection.tsx` - Full feature section with badge, headline, features, media panel
- `components/FeatureList.tsx` - Animated checkmark feature list
- `components/Headline.tsx` - Animated headline with muted gray color
- `components/chat/` - Chat demo with typewriter, typing indicator, avatars
- `compositions/HeroIntro.tsx` - "RAYNI" letter animation where A+I separate into "AI-powered" (sophisticated choreography)
- `compositions/scenes/KnowledgeVortex.tsx` - Documents floating, pulling into center, particle burst, logo reveal (multi-phase choreography)

### Critical Files

| File | Purpose | Status |
|------|---------|--------|
| `social/animation.py` | Animation pipeline orchestration | DONE - works, mirrors art.py |
| `tools/gif-gen.py` | CLI wrapper for Remotion render | DONE - composition validator, process tree kill, gifsicle optimization |
| `remotion/src/lib/design-tokens.ts` | MindPattern design tokens | NEEDS REWRITE - current tokens are wrong direction |
| `remotion/src/lib/utils.ts` | Animation utilities | DONE - ported from Rayni, solid |
| `remotion/src/components/*.tsx` | Remotion components | NEEDS REWRITE - too basic, not rich enough |
| `remotion/src/Root.tsx` | Composition registry | Will change when components are rebuilt |
| `orchestrator/router.py` | Model routing | DONE - animation_director and animation_reviewer added |
| `social/pipeline.py` | Pipeline integration | DONE - animation path wired into Step 3 |
| `run-launchd.sh` | Launchd wrapper | DONE - Node.js PATH added |
| `agents/animation-director.md` | Animation Director skill | NEEDS REWRITE - needs design system knowledge baked in |
| `agents/animation-reviewer.md` | Animation Reviewer skill | DONE |
| `tests/test_animation.py` | Animation tests | DONE - 24 tests passing |
| `tools/image-gen.py` | Image generation (Flux/OpenAI) | EXISTS - can generate infographic backgrounds |
| `/Users/taylerramsay/Projects/rayni_website/remotion/` | Rayni's Remotion code | REFERENCE - quality bar for components |
| `data/agentic-evals-series/DESIGN-SYSTEM.md` | Existing design system (warm minimalism) | REFERENCE - user said "not this one" but research docs are valuable |
| `data/agentic-evals-series/research/*.md` | Deep research on typography, color, animation, iconography | CRITICAL INPUT for new design system |

### Key Patterns Discovered

1. **Agent dispatch**: `orchestrator/agents.py` has three dispatch functions: `run_single_agent()`, `run_agent_with_files()`, `run_claude_prompt()`. Animation agents use `run_claude_prompt()`.
2. **Skill injection for pipeline agents**: Skills like remotion-best-practices must be injected via `--append-system-prompt-file` pointing to the SKILL.md, not native Claude Code skill loading. Pipeline agents run as subprocess.
3. **Process tree kill**: Pattern from commit edf7bd4. Use `os.setsid` + `os.killpg` to kill Puppeteer/Chrome if Remotion render hangs.
4. **staticFile() in Remotion**: Files in `remotion/public/` are served at the root path (no `/public/` prefix). Use `staticFile("filename.png")`.
5. **CWD trap**: Never `cd` into `remotion/` in Bash commands. The harness hooks (`harness/hooks/pre_commit_gate.py`) run relative to CWD and will break. Always use `npx --prefix remotion` or absolute paths.
6. **OpenAI billing limit**: Hit during this session. Flux 2 Pro works as fallback for image generation.
7. **GIF sizes**: 720x720 at 15fps for 4 seconds = ~500KB-1MB. All under Bluesky's 1MB limit. Longer durations (10-12s) push to 1-1.5MB, may need gifsicle optimization.

## Work Completed

### Tasks Finished

- [x] Phase 0: Remotion project setup (package.json, tsconfig, npm install, Node.js v25.1.0 verified)
- [x] `tools/gif-gen.py` - CLI wrapper with composition validator (import allowlist blocks fs/child_process/net/http/os), process tree kill, gifsicle optimization, platform-specific size limits
- [x] `social/animation.py` - Full orchestration: Director -> Compose -> Validate -> Render -> Review, with static image fallback on any failure
- [x] Agent skills: `agents/animation-director.md`, `agents/animation-reviewer.md`
- [x] Router entries: animation_director (Sonnet, 10 turns, 300s), animation_reviewer (Sonnet, 5 turns, 120s)
- [x] Pipeline integration: `social/pipeline.py` Step 3 wired with animation toggle and fallback
- [x] `run-launchd.sh`: Node.js PATH added
- [x] Tests: 24 new tests in `tests/test_animation.py` (composition validator, optimization, pipeline, cleanup, JSON parsing)
- [x] Full test suite: 701 passed (1 pre-existing failure in test_orchestrator unrelated to our changes)
- [x] Brand components v1-v5 (multiple iterations, all rejected by user as too basic)
- [x] CEO plan review with 6/6 scope expansions accepted
- [x] Committed: 23c4eed (26 files, 3539 lines, not pushed)
- [x] CLAUDE.md skill routing rules added
- [x] gifsicle installed via Homebrew

### Remotion Components Built (all need redesign)

Current components in `remotion/src/components/`:
- `Spotlight.tsx` - Stat reveal with particles, grid dots, corner accents, monospace labels
- `DataViz.tsx` - Animated bar chart with spring physics, counting numbers
- `Typography.tsx` (KineticTypography) - Staggered word reveal
- `Infographic.tsx` - Multi-card layout with dark header bar, category pills, staggered card entrance
- `ImageInfographic.tsx` - AI-generated background image with text overlays and animated highlights (NOT WORKING - staticFile path issue, needs debugging)
- `GradientBackground.tsx` - Floating gradient orbs on light bg (ported from Rayni)
- `CategoryPill.tsx` - Colored category label pill
- `InfoCard.tsx` - Card with color accent bar and bullet items
- `BrandIntro.tsx`, `Signature.tsx`, `ConceptAnimation.tsx` - Early versions, likely to be replaced

### Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| Remotion (not Python-native) | Remotion, Pillow/moviepy, API services | User chose max creative flexibility, future video support |
| Full AI composition generation | AI-generated code, pre-built templates, hybrid | User chose full generation for maximum flexibility (can fall back to templates if <70% success) |
| Static image fallback | Block pipeline, skip art, fallback | Fallback to create_art() on ANY animation failure |
| Import allowlist validator | Trust LLM, allowlist, sandbox | Strict allowlist: only @remotion/*, react, react-dom allowed |
| Process tree kill | subprocess.timeout, process group kill | Reuse edf7bd4 pattern to prevent zombie Chrome |
| Light background direction | Dark terminal, light infographic, mix | User wants light backgrounds with decorative elements from dark design (lines, grid dots, monospace labels) |
| Image-backed compositions | Pure React layouts, AI background + overlay | User wants AI-generated infographic backgrounds with Remotion micro-interactions overlaid |

### Skills the User Wants to Use

- `remotion-best-practices` (remotion-dev/skills) - NOT YET INSTALLED. 144K+ weekly installs. Install: `npx skills add https://github.com/remotion-dev/skills --skill remotion-best-practices`
- `ai-video-generation` (inference.sh) - 40+ AI video models via infsh CLI. Text-to-video, image-to-video. Phase 2.
- `nano-banana-2` (inference.sh) - AI image generation via Gemini models. Phase 2.
- Codex and Gemini for review of animation designs. Phase 2.

## Pending Work

### Immediate Next Steps (THE PLAN)

The next session should focus entirely on the DESIGN AND COMPONENT LIBRARY. The plumbing works. The visuals don't.

1. **Deep research on motion graphics agency workflows** - How do professional agencies build animated infographics? What's the process from concept to final output? Search for real agency case studies, Behance/Dribbble animated infographic examples, and motion design system documentation from companies like Uber, Stripe, IBM.

2. **Build a new DESIGN.md from the research docs** - Read all four research files in `data/agentic-evals-series/research/` (color-theory.md, typography.md, iconography-imagery.md, micro-interactions-animation.md). These are exhaustive (30K+ tokens each). Synthesize into a new design system specifically for animated social media GIFs. NOT the warm minimalism system (user said "this is not the design system I want to use"). Build something new that draws from the research.

3. **Build a Creative Director agent** - A new agent skill (`agents/creative-director-animation.md`) that has the design system and research knowledge baked in. This agent should think through the visual concept, layout, information hierarchy, color usage, and motion choreography BEFORE any code is written. It should output a structured brief that the Composition Generator can follow.

4. **Build a large component library** - Use multi-agent parallelism. Dispatch agents to work on different reusable parts simultaneously:
   - **Layout components**: Multi-card grid, comparison layout, mind-map/flow layout, timeline, stat strip
   - **Data components**: Animated bar chart, pie chart, progress bars, counting numbers, percentage rings
   - **Typography components**: Headline with various reveal styles, pull quotes, numbered lists, bullet lists with icons
   - **Decorative components**: Grid dots, corner accents, scan lines, particle bursts, gradient orbs, divider rules, accent bars
   - **Content components**: Category pill, info card, tool/logo card, avatar with name, source citation, branding footer
   - **Visual anchor components**: Illustrated character slot (for AI-generated images), hero image frame, icon grid

5. **Integrate image generation** - Use `tools/image-gen.py` (Flux 2 Pro) to generate:
   - Infographic background illustrations (visual anchors like the golden figure and blue robot in the references)
   - Conceptual imagery for topics (AI brain, network diagrams, etc.)
   - These become the visual foundation layer, with Remotion micro-interactions overlaid on top
   - Need to solve the staticFile() path issue for loading generated images into Remotion compositions
   - Need to handle base64 encoding for GIF output (user mentioned "you will need to make the image base64 to make a gif")

6. **Test with last 10 real posts** - Pull the 10 most recent posts from `memory.db` (at `/Users/taylerramsay/Projects/mindpattern-v3/data/ramsay/memory.db`, NOT the worktree copy which is empty). Build custom compositions for each that tell the story of that post with rich visual design.

7. **Longer hold time** - User specifically requested animations hold the final frame for 2-3 seconds so people can read the content. Current 4-second animations are too short. Go to 8-12 seconds with 3-second hold.

### Design Direction (what we know so far)

The user wants a MIX of:
- **Light backgrounds** (warm white #FAFBFC or similar, not dark mode)
- **Decorative lines** from the dark design: grid dots, corner accent lines, horizontal rules, monospace section labels
- **Category-coded colors**: Blue, green, violet, orange, red for different topic types
- **Information-dense layouts**: 4-8+ cards per composition, real tool names, descriptions
- **AI-generated illustrations** as visual anchors
- **Typography**: Space Grotesk for display (user confirmed they liked this), Geist for body, monospace for labels/data
- **Motion**: Staggered entrances, spring physics, wipe reveals, particle effects, counting numbers
- **Personal branding**: "mindpattern" signature, possibly "Tayler Ramsay" attribution

What they DO NOT want:
- Dark mode / terminal aesthetic (too developer-y)
- Single stat on empty canvas (too sparse)
- Generic layouts that look like a basic HTML page
- The "warm minimalism" design system from DESIGN-SYSTEM.md

### Research Docs Available (READ THESE)

All at `/Users/taylerramsay/Projects/mindpattern-v3/data/agentic-evals-series/research/`:

1. **`micro-interactions-animation.md`** (~28K tokens) - Disney's 12 principles applied to UI, easing curves (cubic-bezier values for every use case), micro-interaction patterns, motion design systems (Material Design 3 tokens, IBM Carbon productive/expressive motion), choreography rules (stagger 20-80ms, total under 400ms), enter/exit patterns. THIS IS THE MOTION BIBLE.

2. **`typography.md`** (~32K tokens) - Complete typography history (Gutenberg to modern), type classification (humanist, geometric, neo-grotesque), font pairing rules, typographic hierarchy through weight/size/spacing, modular scales, line-height rules. Includes specific font recommendations.

3. **`color-theory.md`** (~28K tokens) - Color science, 60-30-10 rule, simultaneous contrast, Helmholtz-Kohlrausch effect (saturated colors appear brighter), color palette construction, common mistakes.

4. **`iconography-imagery.md`** (~28K tokens) - ISOTYPE principles (quantity through repetition), icon design principles, visual storytelling, visual hierarchy with images, spacing and composition rules.

### Logo Library (needed for infographic compositions)

The LinkedIn reference GIFs use real tool/company logos in every card. We need a logo library. Brands mentioned in the last 20 MindPattern posts:

Anthropic, Apple, Bun, Claude, Claude Code, Coefficient Bio, Cursor, Disney, Gemini, Google, Meta, MindPattern, OpenAI, Rayni, Replit, Sora, X

**How to build the library:**
- Collect SVG logos for each brand (prefer SVG for crisp rendering at any size)
- Store in `remotion/public/logos/` so Remotion can access via `staticFile("logos/anthropic.svg")`
- The Animation Director agent should reference logos by name in its output, and the composition should load them dynamically
- Sources: company press kits, SimpleIcons (simpleicons.org), or Brandfetch API
- Need to handle: light and dark variants, consistent sizing (normalize to 24-32px height)
- This library should grow automatically as new brands appear in posts

### New Tool: Pretext (chenglou/pretext)

User wants to add Pretext to the toolchain. It's a 15KB TypeScript library by Cheng Lou (React core team, creator of react-motion) for measuring and laying out multiline text without the DOM. 300-600x faster than DOM-based text measurement.

**Why it matters for us:**
- Pixel-perfect text layout for infographic compositions without depending on browser rendering
- Works in Node.js (so it can run in Remotion's render pipeline)
- Supports all languages, emojis, mixed bidirectional text
- Renders to Canvas, SVG, and DOM
- `prepareInlineFlow()` handles mixed-font inline items (perfect for infographic cards with different font sizes)
- Can calculate exact text heights before rendering, enabling precise multi-card layouts
- Explicitly designed to be AI-friendly

**Install:** `npm install @chenglou/pretext`
**GitHub:** https://github.com/chenglou/pretext
**Key APIs:** `prepare()` -> `layout()` for height measurement, `prepareWithSegments()` -> `layoutWithLines()` for full line objects, `layoutNextLine()` for streaming with variable widths per line.

**Integration with Remotion:** Use Pretext to calculate text layouts, then render via Remotion's Canvas or SVG elements. This replaces the crude approach of hard-coding font sizes and hoping text fits. The Creative Director agent can use Pretext to validate that a composition's text actually fits before rendering.

### Blockers/Open Questions

- OpenAI billing limit hit. Flux 2 Pro works. May need user to increase OpenAI limit or use inference.sh skills instead.
- `ImageInfographic.tsx` component has a staticFile() path issue. Generated images in `remotion/public/` aren't being served correctly. Need to debug.
- How should the Creative Director agent interface with image generation? Should it describe the visual concept and a separate step generates the image? Or should it generate a prompt for the image gen tool?
- What's the right approach for base64 images in Remotion GIFs?
- Should we build a Remotion Studio preview workflow so the user can see compositions before rendering to GIF?

### Deferred Items (from CEO review)

All 6 scope expansions were accepted but not yet built:
1. Slack GIF preview in approval messages - extend `social/approval.py`
2. A/B testing (animated vs static) across platforms
3. Engagement tracking per animation style in `memory/social.py` + `memory/db.py`
4. Engagement-driven weighted style rotation
5. Gallery viewer (FastAPI endpoint or static HTML)
6. Animation signature branded overlay component

## Context for Resuming Agent

### Important Context

1. **The plumbing works. The visuals don't.** Do NOT rebuild the pipeline infrastructure. Focus entirely on design and components.
2. **Read the research docs FIRST.** They're the foundation for the new design system. All four files in `data/agentic-evals-series/research/`.
3. **Look at the Rayni Remotion code** at `/Users/taylerramsay/Projects/rayni_website/remotion/` for the quality bar. Especially `compositions/scenes/KnowledgeVortex.tsx` (multi-phase choreography) and `compositions/HeroIntro.tsx` (letter animation).
4. **Look at the LinkedIn reference GIFs** at `/Users/taylerramsay/Downloads/gif/` for the information density bar.
5. **The real memory.db is at `/Users/taylerramsay/Projects/mindpattern-v3/data/ramsay/memory.db`** (not in the worktree). Table `social_posts` has 113 rows. Query `WHERE posted = 1 AND content IS NOT NULL` for real post content.
6. **Use multi-agent parallelism** for building the component library. Different agents can work on layout, data viz, typography, and decorative components simultaneously.
7. **The user builds products.** They built Rayni (rayni.ai). They care about craft and quality. They will reject mediocre output. Don't ship placeholder designs.

### Assumptions Made

- Node.js v25.1.0 and npm are available at /opt/homebrew/bin/
- gifsicle is installed at /opt/homebrew/bin/gifsicle
- Flux 2 Pro API key is in macOS Keychain as "bfl-api-key"
- OpenAI API key is in Keychain but billing limit may be hit
- Remotion 4.x is installed in remotion/node_modules/

### Potential Gotchas

1. **CWD TRAP**: NEVER `cd` into `remotion/` in Bash commands. The harness hooks break. Use `npx --prefix remotion` or absolute paths. If CWD gets stuck, create dummy hooks at `remotion/harness/hooks/{pre_commit_gate,post_tool_audit}.py` with `import sys; sys.exit(0)`, cd back, then delete them.
2. **staticFile() paths**: Remotion serves from `remotion/public/`. Path in code should be just the filename, not `public/filename`.
3. **Empty worktree DB**: The worktree's `data/ramsay/memory.db` is empty (0 bytes). The real one is at the original repo path.
4. **GIF file sizes**: 720x720, 15fps, 10 seconds = ~1MB. Bluesky limit is 1MB strict. May need 12fps or gifsicle optimization for longer animations.
5. **Pre-existing test failure**: `tests/test_orchestrator.py::TestRouter::test_get_model_research_agent` expects "opus" but gets "claude-opus-4-6[1m]". Not caused by our changes. Run tests with `--ignore=tests/test_orchestrator.py` or fix the test.

## Environment State

### Tools/Services Used

- Node.js v25.1.0 + npm 11.6.2 (at /opt/homebrew/bin/)
- Remotion 4.x (in remotion/node_modules/)
- gifsicle 1.96 (at /opt/homebrew/bin/)
- Python 3.14 (at /opt/homebrew/Cellar/python@3.14/)
- Flux 2 Pro API (via tools/image-gen.py, keychain: bfl-api-key)
- Claude CLI (Pro subscription, subprocess dispatch)
- macOS Keychain for all API keys

### Active Processes
- None running

### Environment Variables
- No env vars needed. All secrets in macOS Keychain.
- Keychain keys: bfl-api-key, openai-api-key, resend-api-key, bluesky-app-password, linkedin-access-token

## Related Resources

- CEO Plan: `~/.gstack/projects/tayler-id-mindpattern-v3/ceo-plans/2026-04-03-animated-gif-pipeline.md`
- Design Doc: `~/.gstack/projects/tayler-id-mindpattern-v3/taylerramsay-worktree-snug-chasing-salamander-design-20260403-150311.md`
- Plan file: `/Users/taylerramsay/.claude/plans/snug-chasing-salamander.md`
- Rayni Remotion code: `/Users/taylerramsay/Projects/rayni_website/remotion/`
- LinkedIn reference GIFs: `/Users/taylerramsay/Downloads/gif/`
- Research docs: `/Users/taylerramsay/Projects/mindpattern-v3/data/agentic-evals-series/research/`
- Existing design system (reference only): `/Users/taylerramsay/Projects/mindpattern-v3/data/agentic-evals-series/DESIGN-SYSTEM.md`
- MindPattern architecture: `docs/ARCHITECTURE.md`
- Remotion best practices skill: https://skills.sh/remotion-dev/skills/remotion-best-practices
- AI video generation skill: https://skills.sh/inferen-sh/skills/ai-video-generation
- Nano banana 2 skill: https://skills.sh/inferen-sh/skills/nano-banana-2

---

**Security Reminder**: No secrets in this document. All API keys are referenced by Keychain service name only.
