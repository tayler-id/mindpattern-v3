# Spec and Runbook: Features 17, 18, 20, and 21 - Arcs, Angles, Audio, and Video Scripts

> Status: Implemented locally through Task 20; release hygiene in progress
> Owner: Tayler
> Author: Codex
> Created: 2026-06-28
> Source evidence: `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
> Feature rows: 17, 18, 20, 21 in the "30 Pure New Feature Ideas" table
> Implementation plan: `docs/runbooks/2026-06-28-features-17-18-20-21-media-arcs-implementation-plan.md`

This runbook specifies four related MindPattern v3 features:

- Feature 17: Narrative Arc Builder
- Feature 18: Social Angle Lab
- Feature 20: Audio Morning Briefing
- Feature 21: Short-Form Video Script Mode

## Implementation Status - 2026-06-28

Local implementation is complete through Task 20 in the paired implementation
plan:

- Feature 17 creates source-backed narrative arc artifacts and exposes safe
  public arc API output. Arcs are injected only into synthesis pass 2 as
  enrichment context and never alter pass-1 story selection.
- Feature 18 returns critic-ranked Social Angle Lab candidates in `#mp-posts`
  and hands `draft <n>` into the existing approval-gated social draft path.
- Feature 20 builds deterministic audio briefing metadata/artifacts in v3,
  exposes safe public audio endpoints, and renders audio players in the Rabbit
  Hole website via the v3 public API.
- Feature 21 returns Slack-ready short-form video script packages from
  `#mp-posts`, including `video angle <n>` handoff after a Social Angle Lab
  result, with AI-assisted/manual-publish labels and source evidence.
- Slack file artifact upload support exists as a tested helper using Slack's
  external upload flow; live upload/smoke still requires owner approval.
- No full daily pipeline, newsletter send, Fly deploy, Vercel deploy, live
  Slack smoke, live social post, schema change, dependency install, or real
  TTS/video provider call was run during this implementation.

The user explicitly changed Feature 20 from "dashboard" to the public Rabbit
Hole website at `/Users/taylerramsay/Projects/mindpattern-rabbit-hole`, which
is a Vercel-hosted Next.js app. Feature 21 should start by posting Slack-ready
video packages to Slack so the owner can manually publish them to social
platforms.

## Model / Execution Requirement

Owner update on 2026-06-28: before substantial implementation continues, this
runbook and the implementation plan should be run or reviewed with Opus 4.8.
Codex sessions cannot switch their own model. If the active execution
environment is not Opus 4.8, record that explicitly in the implementation
plan's Done table and continue only with owner approval or after restarting the
goal in an Opus 4.8-capable environment.

## Assumptions

1. Feature numbers refer to the "30 Pure New Feature Ideas" table in the
   2026-06-26 handoff.
2. These are new-feature specs. They must not weaken the already-repaired
   newsletter quality gates, source health checks, Slack approval parsing, or
   Ask Follow-Up safeguards.
3. Feature 20 publishes audio briefing output to the website, not to the old
   dashboard UI. The v3 backend remains the generation and public API source.
4. Feature 21 starts as Slack-delivered video script packages. Actual MP4
   generation is a later provider adapter and requires explicit owner approval
   if it adds dependencies, credentials, paid APIs, or new storage.
5. No live social platform post is allowed without explicit owner approval in
   Slack.
6. No schema changes, deploys, full daily pipeline runs, external media
   provider setup, or public website writes happen during this spec pass.

## Current System Read

MindPattern v3:

- Daily runner is in `orchestrator/runner.py`.
- Newsletter reports are written under `reports/ramsay/YYYY-MM-DD.md`.
- Public API routes are in `dashboard/routes/api.py`.
- Memory uses SQLite via `memory/db.py`, including `findings`, `patterns`,
  `entity_graph`, `social_posts`, `social_feedback`, `agent_notes`, and
  `run_quality`.
- Slack #mp-posts is handled by `slack_bot/handlers/posts.py`.
- #mp-posts already runs Creative Director -> writers -> critics -> policy ->
  humanizer -> expeditor, then waits for Slack approval before posting.
- Ask Follow-Up is already implemented locally and in CI for Feature 24.

Rabbit Hole website:

- Repo: `/Users/taylerramsay/Projects/mindpattern-rabbit-hole`
- Stack: Next.js 16, React 19, App Router, TypeScript, Tailwind v4.
- Backend helper: `src/lib/api.ts` calls `https://mindpattern.fly.dev`.
- Briefing list: `src/app/(app)/briefings/page.tsx`
- Briefing detail: `src/app/(app)/briefings/[date]/page.tsx`
- Types: `src/lib/types.ts`
- Current briefing pages render report markdown from the v3 `/api/reports`
  endpoints.

## Research Sources

Use these as current implementation references:

- OpenAI Text-to-Speech: `https://developers.openai.com/api/docs/guides/text-to-speech`
- OpenAI Video generation: `https://developers.openai.com/api/docs/guides/video-generation`
- Slack external file upload: `https://docs.slack.dev/reference/methods/files.getUploadURLExternal/`
- Slack upload completion: `https://docs.slack.dev/reference/methods/files.completeUploadExternal/`
- Vercel Blob: `https://vercel.com/docs/vercel-blob`
- Vercel Slack bot with Blob approval-gated file tools:
  `https://vercel.com/kb/guide/slack-bot-vercel-blob`
- Next.js Route Handlers:
  `https://nextjs.org/docs/app/api-reference/file-conventions/route`
- Next.js public folder:
  `https://nextjs.org/docs/app/api-reference/file-conventions/public-folder`
- C2PA specs: `https://spec.c2pa.org/specifications/specifications/2.2/index.html`
- C2PA tool: `https://opensource.contentauthenticity.org/docs/c2patool/`
- W3C PROV overview: `https://www.w3.org/TR/prov-overview/`
- Microsoft GraphRAG docs: `https://microsoft.github.io/graphrag/`
- Graphiti temporal knowledge graph docs:
  `https://help.getzep.com/graphiti/getting-started/overview`
- OWASP Top 10 for LLM Applications:
  `https://owasp.org/www-project-top-10-for-large-language-model-applications/`
- Remotion render docs: `https://www.remotion.dev/docs/render/`
- FFmpeg docs: `https://ffmpeg.org/ffmpeg.html`
- Poynter story focus guidance:
  `https://www.poynter.org/reporting-editing/2003/selling-the-power-of-focus/`
- Poynter nut graf guidance:
  `https://www.poynter.org/archive/2003/the-nut-graf-part-i/`
- NPR Public Editor journalism quality rubric:
  `https://www.npr.org/sections/npr-public-editor/2025/05/01/g-s1-63806/when-journalists-talk-about-great-journalism-heres-what-they-mean`
- Media Helping Media news-angle checklist:
  `https://mediahelpingmedia.org/quick-guides/quick-guide-developing-news-angles/`
- LinkedIn thought leadership guidance:
  `https://www.linkedin.com/business/marketing/blog/content-marketing/creating-a-thought-leadership-marketing-plan`

## Agent Reach Status

`agent-reach doctor --json` on 2026-06-28 reported:

- `exa_search`: ok via Exa/mcporter.
- `web`: ok via Jina Reader.
- `twitter`: ok via twitter-cli.
- `youtube`: ok via yt-dlp.
- `rss`: ok via feedparser.
- `reddit`: warn; OpenCLI installed but Chrome extension still missing.
- `linkedin`: off; LinkedIn MCP not configured.

Do not make these features depend on Reddit or LinkedIn search being live.
They should degrade visibly when a source backend is unavailable.

## Non-Goals

- Do not create a dashboard implementation for Feature 20.
- Do not make Slack approval required for the daily newsletter to research,
  write, or send.
- Do not auto-post audio, video, or social content to external platforms.
- Do not create a hidden second newsletter pipeline.
- Do not let narrative arcs add, remove, reorder, replace, or gate selected
  newsletter stories. Feature 17 is enrichment-only.
- Do not add a new graph database for the MVP.
- Do not write public files into the website repo from the daily runner.
- Do not commit generated audio, video, Slack message bodies, databases,
  `users.json`, `social-config.json`, subscriber data, secrets, or raw tokens.
- Do not use custom voice cloning unless the owner explicitly approves consent
  handling and provider terms.

## Shared Contracts

All four features should use structured contracts instead of free-form strings.

### Evidence Reference

```python
evidence = {
    "finding_id": 123,
    "run_date": "2026-06-28",
    "agent": "vibe-coding-researcher",
    "title": "Story title",
    "summary": "Short summary",
    "source_url": "https://example.com/source",
    "source_name": "Example",
}
```

### Public Artifact Metadata

```python
artifact = {
    "id": "2026-06-28-audio-morning-briefing",
    "date": "2026-06-28",
    "type": "audio_briefing",
    "title": "MindPattern Morning Briefing - June 28, 2026",
    "status": "ready",
    "public_url": "https://mindpattern.fly.dev/api/audio-briefings/2026-06-28/file",
    "transcript_url": "https://mindpattern.fly.dev/api/audio-briefings/2026-06-28/transcript",
    "duration_seconds": 240,
    "source_report_date": "2026-06-28",
    "source_report_url": "https://mindpattern.ai/briefings/2026-06-28",
    "source_count": 8,
    "ai_generated": True,
    "provenance": {
        "provider": "openai",
        "model": "gpt-4o-mini-tts",
        "voice": "marin",
        "c2pa_manifest": None,
        "sidecar_json": "reports/ramsay/audio/2026-06-28.provenance.json"
    }
}
```

### Slack Media Package

```python
package = {
    "id": "video-script-2026-06-28-001",
    "story_title": "Story title",
    "story_url": "https://example.com/source",
    "duration_seconds": 45,
    "hook": "Opening line",
    "script": "Spoken script",
    "shot_list": [
        {"time": "0-5s", "visual": "Title card", "notes": "Show source title"}
    ],
    "caption": "Manual social caption",
    "source_urls": ["https://example.com/source"],
    "labels": ["AI-assisted script", "manual publish only"],
    "status": "draft",
}
```

## Feature 17: Narrative Arc Builder

### Objective

Track multi-day arcs such as "AI IDEs consolidate" or "agent governance becomes
a category" so the newsletter can include deeper context than isolated daily
stories.

### User Value

Readers should see when a story is part of a pattern that has been building for
days or weeks. Tayler should be able to ask "what arc is this part of?" and get
evidence trails with dates, sources, agents, and related findings.

### MVP Behavior

- Scan the last 14-30 days of findings, reports, patterns, and entity graph
  relationships.
- Cluster related high-signal findings by embedding similarity, entity overlap,
  source diversity, and temporal recurrence.
- Assign stable arc IDs based on canonical theme and hash.
- Score each arc by recurrence, velocity, source diversity, evidence quality,
  freshness, and novelty.
- Emit daily arc candidates to `reports/ramsay/arcs/YYYY-MM-DD.json`.
- Provide `get_narrative_arcs(date, limit)` for synthesis and public API use.
- Include an evidence trail for every arc. No source trail means no arc.
- Inject arcs only into synthesis pass 2 / narrative context. Arcs must never be
  passed into `_balance_story_candidates()` or the pass-1 story-selection prompt.

### Trusted/Safe/Hardened Requirements

- Every arc must have at least 3 evidence items across at least 2 dates.
- A "strong" arc must have at least 2 source domains or 2 contributing agents.
- Do not synthesize unsupported claims; arc summaries must cite evidence IDs.
- Arcs never add, remove, reorder, replace, or gate selected newsletter stories.
- Mark arcs `emerging`, `active`, `stale`, or `archived`.
- Store only safe public evidence fields in artifacts.
- Log trace events for arc extraction count, degraded source reasons, and
  rejected arc count.

### Likely Files

- `orchestrator/arcs.py`
- `orchestrator/runner.py`
- `dashboard/routes/api.py`
- `memory/graph.py`
- `memory/patterns.py`
- `tests/test_narrative_arcs.py`
- `tests/test_api_contract.py`

### Acceptance Criteria

- Given fixture findings across multiple days, the builder returns stable arcs
  with evidence trails.
- Single-day duplicates do not become arcs.
- A stale arc is not injected into synthesis unless it has fresh evidence.
- Pass-1 selected story IDs/titles are identical with and without arcs for the
  same fixture input.
- Public API returns sanitized arc summaries and no private DB fields.

## Feature 18: Social Angle Lab

### Objective

For any story, finding, arc, URL, or Slack draft, generate multiple social
angles such as contrarian take, builder lesson, market take, tactical tip,
launch note, and short-video hook.

### User Value

The Slack bot should give richer choices without auto-posting. Tayler can ask
for angle variants, choose one, and then run the existing #mp-posts draft
pipeline with explicit Slack approval.

### MVP Behavior

- Accept Slack commands in `#mp-posts`:
  - `angles: <topic or URL>`
  - `angles finding <id>`
  - `angles arc <arc_id>`
  - `angle lab: <topic>`
- Generate 4-6 angle candidates with hook, target platform, source URLs,
  confidence, and risk notes.
- Run an assignment-editor-style Angle Critic before Slack output. The critic
  scores and cuts candidates before any social writer agent drafts a post.
- Store safe JSON only under `reports/ramsay/social-angles/YYYY-MM-DD.json`.
  Do not use `data/social-angles/`; `data/` is not ignored and may commit
  internal angle content.
- Let `draft <n>` hand the chosen angle to `PostsHandler._run_and_approve()`.
- Let `video <n>` hand the chosen angle to Feature 21's video script mode.

### Angle Critic Design

The Angle Critic is not a copy editor and not a generic social-media optimizer.
It is a skeptical assigning editor. Its job is to decide whether an angle is
worth a writer's time.

Research-backed editorial principles:

- Poynter's story-focus guidance asks whether the story matters, what the point
  is, why it is being told, and what it says about the current moment.
- Poynter's nut-graf guidance treats the core angle as the promise to the
  reader: why this story is worth attention and why it matters now.
- NPR's journalism-quality rubric emphasizes audience need, moving the dialogue
  forward, clarity without lost nuance, research depth, diverse sourcing,
  fairness, and fact-checking.
- Media Helping Media's angle checklist emphasizes looking past the surface,
  checking facts beyond press releases, following money/incentives, using data
  to find patterns, asking difficult questions, considering long-term effects,
  and staying ethical.
- LinkedIn's thought-leadership guidance emphasizes fresh perspective, audience
  relevance, trust, concision, usefulness, decision-maker value, and ongoing
  conversation.

The critic must score each candidate on these dimensions:

| Dimension | What the critic checks | Fail condition |
|---|---|---|
| Focus | One dominant meaning, not a pile of related facts. | More than one thesis or listicle framing. |
| Why now | Timely reason this should be said today. | Could have been posted any day. |
| Audience value | Clear benefit for builder/operator/decision-maker readers. | Interesting only to the author or too niche without payoff. |
| Evidence strength | Claim maps to source URLs, findings, or arc evidence. | Unsupported claim, vague source, or source does not prove the angle. |
| Freshness / non-repeat | Not too close to recent posts or newsletter repeats. | Same angle already used recently. |
| Tension | Contains real contrast, conflict, surprise, tradeoff, or consequence. | Merely summarizes the original story. |
| Specificity | Names concrete tools, companies, numbers, behaviors, or workflow details. | Generic AI/social commentary. |
| Platform fit | Native to LinkedIn, Bluesky, or video script use. | Same framing pretending to fit every platform. |
| Tayler fit | Sounds like a senior builder/designer/operator observation, not a product ad. | Product pitch, fake persona, or generic influencer voice. |
| Risk / calibration | Confidence matches evidence and uncertainty is named. | Overclaiming, certainty theater, or legal/reputation risk. |

Each candidate should receive:

```json
{
  "angle_id": "angle_2",
  "verdict": "keep | revise | reject",
  "score": 8.1,
  "scores": {
    "focus": 9,
    "why_now": 8,
    "audience_value": 8,
    "evidence_strength": 9,
    "freshness": 7,
    "tension": 8,
    "specificity": 8,
    "platform_fit": 8,
    "tayler_fit": 9,
    "risk_calibration": 7
  },
  "reason": "One sharp builder lesson with source-backed tension.",
  "revision_note": "Name the exact source-health failure before drafting.",
  "kill_switches": []
}
```

Hard kill switches:

- No source-backed evidence.
- No clear why-now.
- Same angle as a recent post.
- Product-pitch framing.
- Unsupported factual claim.
- Generic "AI is changing everything" framing.
- Platform-generic framing with no native fit.
- Manufactured controversy unsupported by the evidence.

Slack should show only kept/revised angles ranked by score. Rejected angles can
be stored in the artifact for audit, but should not be shown as draft choices
unless Tayler asks for `show rejected`.

The selected angle becomes a structured creative input for the existing social
pipeline. The Angle Critic does not write the final post and must not bypass
Creative Director, platform writers, critics, policy validation, humanizer, or
expeditor.

### Existing Prompt Conflict to Resolve

Before implementing Feature 18, reconcile the current social-agent guidance:

- `agents/expeditor.md` rewards specific builder credibility and treats concrete
  infrastructure references as a quality signal.
- `social/writers.py` currently forbids several infrastructure phrases such as
  "I run agents", "my pipeline", "cron job", and related wording.

Feature 18 must not ship while those rules disagree. The implementation should
define a single owner-approved boundary between good practitioner transparency
and bad product-pitch/self-promotional framing, then update tests/prompts around
that boundary.

This owner-approved boundary is required before Task 8 starts. Until then,
Feature 18 implementation must stop after parser/contract work.

### Trusted/Safe/Hardened Requirements

- This feature creates angle candidates only. It never publishes live.
- `draft <n>` must enter the existing social approval loop.
- Unclear replies change no state.
- Angles must carry source URLs or be marked "needs source".
- Do not store raw Slack message bodies or private user IDs.
- Reject newsletter-control commands such as `send newsletter` or
  `approve story`.

### Likely Files

- `orchestrator/social_angles.py`
- `slack_bot/handlers/posts.py`
- `slack_bot/handlers/social_ideas.py` if Social Ideas Desk is present later
- `tests/test_social_angle_lab.py`
- `tests/test_slack_bot.py`
- `tests/test_social.py`

### Acceptance Criteria

- `angles: <topic>` returns angle variants in a Slack thread.
- `draft 2` creates a normal #mp-posts approval draft, not a live post.
- `video 1` creates a Feature 21 script package in Slack.
- Tests prove no newsletter send and no live social post can occur.

## Feature 20: Audio Morning Briefing to Website

### Objective

Generate a 3-5 minute spoken briefing from the daily issue or top research and
publish it to the Rabbit Hole website, not the old dashboard.

### User Value

Readers can play the morning briefing on the public site. Tayler gets a durable
transcript, source notes, and provenance for trust.

### Recommended Architecture

Use v3 as the generation and public API source. Use the Rabbit Hole site as the
presentation layer.

```text
daily report markdown
    -> audio script builder
    -> TTS provider adapter
    -> audio/transcript/provenance artifacts
    -> v3 public read-only API
    -> Rabbit Hole audio player on /briefings and /briefings/[date]
```

This is safer than having v3 write files into the Vercel site repo. The site
already pulls live v3 data through `src/lib/api.ts`.

### MVP Behavior

- After synthesis produces `reports/ramsay/YYYY-MM-DD.md`, build a
  voice-friendly script from the report.
- Script must be plain spoken prose. No markdown tables, raw URLs, or code
  blocks in the speech text.
- Generate an MP3 with a provider adapter. The first adapter can be OpenAI TTS
  because the official docs support `gpt-4o-mini-tts`, built-in voices, MP3
  output, and streaming or file output.
- Write:
  - `reports/ramsay/audio/YYYY-MM-DD.mp3`
  - `reports/ramsay/audio/YYYY-MM-DD.transcript.md`
  - `reports/ramsay/audio/YYYY-MM-DD.json`
  - `reports/ramsay/audio/YYYY-MM-DD.provenance.json`
- Add public read-only v3 endpoints:
  - `GET /api/audio-briefings?user=ramsay`
  - `GET /api/audio-briefings/{date}?user=ramsay`
  - `GET /api/audio-briefings/{date}/file?user=ramsay`
  - `GET /api/audio-briefings/{date}/transcript?user=ramsay`
- Add Rabbit Hole site helpers/types/components:
  - `getAudioBriefings()`
  - `getAudioBriefing(date)`
  - `AudioBriefingPlayer`
  - audio player on `/briefings`
  - audio player on `/briefings/[date]`

### Storage Decision

MVP should serve audio from the v3 backend with strict path validation. Vercel
Blob is a strong later option, especially if the site becomes the canonical
asset host, but it adds token and write-operation concerns. If Vercel Blob is
used later, use immutable object names and approval-gated writes.

### Trusted/Safe/Hardened Requirements

- Do not generate audio when the source newsletter is missing, degraded below
  quality floor, or contains a visible degraded header unless the audio also
  carries that degraded label.
- Do not read from private DB fields for public metadata.
- Public file endpoint must validate `YYYY-MM-DD` and user path segments.
- No directory traversal, no `/data` static mount, no arbitrary file serving.
- Audio page must show "AI-generated audio" and link the source report.
- Store a provenance sidecar with source report hash, TTS provider, model,
  voice, generated timestamp, and script hash.
- Optional later: sign media with C2PA/c2patool when the tool and certificate
  are approved. Do not block MVP on C2PA signing.
- Do not use custom cloned voices without explicit owner approval and consent.

### Likely Files

MindPattern v3:

- `orchestrator/audio_briefing.py`
- `orchestrator/runner.py`
- `dashboard/routes/api.py`
- `tests/test_audio_briefing.py`
- `tests/test_api_contract.py`

Rabbit Hole:

- `src/lib/types.ts`
- `src/lib/api.ts`
- `src/components/briefing/audio-briefing-player.tsx`
- `src/app/(app)/briefings/page.tsx`
- `src/app/(app)/briefings/[date]/page.tsx`

### Acceptance Criteria

- Dry-run creates deterministic transcript and metadata without calling TTS.
- Missing/degraded report creates a visible degraded metadata record or skips
  audio with a trace event.
- Public API lists audio briefings and streams only valid MP3 files.
- Rabbit Hole site shows an audio player for dates with audio and no broken UI
  for dates without audio.

## Feature 21: Short-Form Video Script Mode

### Objective

Convert a selected story into a 30-60 second short-form video package and post
it to Slack so Tayler can manually publish it to social platforms.

### User Value

The system turns strong research into a reusable video script, shot list,
caption, and source-backed production notes without forcing automated social
publishing.

### MVP Behavior

- Accept commands in `#mp-posts`:
  - `video script: <topic or URL>`
  - `video finding <id>`
  - `video arc <arc_id>`
  - `video angle <n>` from Feature 18 thread state
- Return in the Slack thread:
  - 30, 45, or 60 second duration.
  - Hook.
  - Spoken script.
  - Shot list.
  - B-roll/source note list.
  - Manual caption.
  - Suggested platform framing.
  - Evidence/source URLs.
  - Risk labels and "manual publish only".
- Write safe artifact:
  - `reports/ramsay/video-scripts/YYYY-MM-DD-<slug>.json`
  - `reports/ramsay/video-scripts/YYYY-MM-DD-<slug>.md`
- Upload artifact files to Slack using Slack's current external upload flow
  when file upload is needed.

### Future MP4 Phase

Actual MP4 generation is not required for MVP. If implemented later, prefer a
deterministic template pipeline first:

- Remotion for React-based templates and server-side rendering.
- FFmpeg for audio/video muxing, transcoding, captions, and format conversion.
- Optional AI video provider adapter only after owner approval.

OpenAI's current video docs support Sora video jobs, progress polling, webhooks,
MP4 download, and prompt specificity. Treat provider-generated video as an
adapter behind the same artifact and safety contract, not as the core workflow.

### Trusted/Safe/Hardened Requirements

- No live social post from this feature.
- No automatic use of real people likeness, cloned voices, copyrighted footage,
  or source screenshots unless the source/license permits it.
- Do not claim generated visuals are real footage.
- Include "AI-assisted script" and "manual publish only" labels in Slack.
- Every factual claim in the script must trace back to a source URL, finding,
  report, or arc evidence item.
- If source evidence is weak, return a degraded script package and ask for
  follow-up research instead of fabricating specificity.
- Uploading to Slack requires `files:write` and should use the parent thread
  timestamp, not a reply timestamp.

### Likely Files

- `orchestrator/video_scripts.py`
- `slack_bot/handlers/posts.py`
- `slack_bot/files.py`
- `tests/test_video_scripts.py`
- `tests/test_slack_bot.py`
- Optional later: `video/` or site-side `remotion/` package only after owner
  approval for dependencies.

### Acceptance Criteria

- `video script: <topic>` returns a phone-readable Slack script package.
- `video finding <id>` uses the finding's source URL and summary as evidence.
- `video angle <n>` works after Feature 18 angle generation.
- Tests prove no live social API call, newsletter send, full daily pipeline run,
  or Fly deploy happens.

## Cross-Feature Safety Model

### Always

- Validate external inputs at Slack/API boundaries.
- Use path validation for dates and user IDs.
- Escape or render markdown safely.
- Keep write operations explicit and traceable.
- Add trace events for generated artifacts, degraded inputs, skipped outputs,
  and Slack file upload failures.
- Keep all public API responses sanitized.
- Use source URLs and evidence IDs as first-class fields.
- Keep generated media labels visible.

### Ask First

- Adding dependencies.
- Adding or migrating database schema.
- Adding provider credentials.
- Uploading generated media to Vercel Blob.
- Deploying to Fly or Vercel.
- Running the full daily pipeline.
- Enabling live social posting.
- Using custom voices, likenesses, or AI video generation providers.

### Never

- Never commit secrets, databases, raw Slack message bodies, subscriber data,
  `users.json`, or `social-config.json`.
- Never silently publish social content.
- Never let these features reduce newsletter quality checks.
- Never serve arbitrary files from `reports/` or `data/`.
- Never fabricate source-backed claims in audio or video scripts.

## Commands

Use these during implementation unless a task says otherwise.

```bash
# Start state
git status --short --branch
git diff --stat

# MindPattern v3 focused tests
.venv/bin/python3 -m pytest tests/test_narrative_arcs.py -q
.venv/bin/python3 -m pytest tests/test_social_angle_lab.py tests/test_social.py -q
.venv/bin/python3 -m pytest tests/test_audio_briefing.py tests/test_api_contract.py -q
.venv/bin/python3 -m pytest tests/test_video_scripts.py tests/test_slack_bot.py -q

# Existing safety regressions
.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_slack_bot.py tests/test_social.py -q
.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q

# Rabbit Hole site checks
pnpm lint
pnpm build

# Docs / graph
git diff --check
graphify update .
graphify check-update .
```

Commands requiring explicit owner approval:

```bash
# Full daily pipeline
.venv/bin/python3 run.py

# Fly deploy / live Slack smoke
/Users/taylerramsay/.fly/bin/flyctl deploy --app mindpattern

# Vercel production deploy from Rabbit Hole
vercel --prod

# Dependency install in either repo
pnpm add <package>
.venv/bin/python3 -m pip install <package>
```

## Open Questions

1. Should audio be public immediately on the website, or should the first week
   be hidden from sitemap/indexing while quality is reviewed?
2. Should Feature 20 publish only after the newsletter is successfully sent, or
   as soon as synthesis passes quality floor?
3. Which Slack channel should own video script requests: existing `#mp-posts`
   only, or a new dedicated video channel later?
4. Should generated media artifacts be stored long-term on the v3 backend or
   moved to Vercel Blob after MVP?

## Ready-To-Paste Goal Prompt

```text
/goal Implement MindPattern v3 Features 17, 18, 20, and 21: Narrative Arc Builder, Social Angle Lab, Audio Morning Briefing to Rabbit Hole, and Short-Form Video Script Mode.

Primary source of truth:
- docs/runbooks/2026-06-28-features-17-18-20-21-media-arcs-runbook.md
- docs/runbooks/2026-06-28-features-17-18-20-21-media-arcs-implementation-plan.md
- .claude/handoffs/2026-06-26-system-audit-slack-social.md

Follow the implementation plan task by task, in dependency order. Do not skip the Done column updates.

Hard requirements:
- Keep Slack-bot-first behavior for social/video workflows.
- No live outbound social post without explicit owner approval in Slack.
- Feature 20 must publish audio to the Rabbit Hole website path through the public v3 API/site integration, not the old dashboard UI.
- Feature 21 starts by posting Slack-ready video script packages to Slack; actual MP4 generation is optional and requires owner approval for dependencies/providers.
- Do not make Slack approval required for the normal daily newsletter to research, write, or send.
- Do not run the full daily pipeline, deploy to Fly, deploy to Vercel, add dependencies, add provider credentials, or change schema without explicit owner approval.
- Dry-run/focused tests must not call Claude, network, Slack, email, social APIs, Fly, Vercel, TTS/video providers, or private local databases.
- Do not expose or commit secrets, personal data, raw Slack message bodies, subscriber data, databases, users.json, social-config.json, generated audio/video files, or provider tokens.
- Generated audio/video/script output must carry source evidence and visible AI-generated/manual-publish labels.
- Public media endpoints must validate dates/user IDs and never serve arbitrary files.

Execution rules:
- Start by recording current dirty files in both repos and baseline focused tests.
- For each task: write/update tests first, implement the smallest change, run the task verification command, then update the Done column and evidence.
- Preserve unrelated user changes in both repositories.
- Work in small commits by verified phase or task group.
- After code/docs changes, run Graphify where required.
- Before final response, report tests run, commits made, deploy/smoke status, unresolved blockers, and current git status for both repos.

Definition of done:
- Feature 17 creates source-backed narrative arc artifacts and public sanitized API output.
- Feature 18 returns social angle variants in Slack and can hand selected angles to the existing approval-gated social draft path.
- Feature 20 generates deterministic dry-run audio metadata, supports real TTS behind an explicit provider boundary, exposes safe public audio endpoints, and renders audio players on Rabbit Hole briefing pages.
- Feature 21 returns Slack-ready short-form video script packages with source evidence, captions, shot lists, and manual-publish labels.
- All focused and safety regression tests pass locally or are clearly blocked by an external dependency.
- Handoff and runbook are current for the next agent.
- Repos are clean or dirty files are clearly explained.
```
