# Spec: MindPattern CampaignOS v2 — four-campaign pilot

- **Status:** **Approved by Tayler on 2026-07-12** (Decisions 1–5 and 7–9 as recorded; Decision 6 open, due before campaign 1 launch). Approval authorizes Phase 2 planning only; implementation is **not authorized** until the Phase 2 plan is separately approved
- **Date:** 2026-07-11
- **Revised:** 2026-07-12 — second adversarial review (repository-verified) reconciled
- **Owner/operator:** Tayler
- **Primary repository:** `campaignos` — a new standalone project at `~/Projects/campaignos`, created in Phase 2. This spec lives in `mindpattern-v3/docs/specs/` until that repo exists, then a copy moves with it.
- **Content source:** `mindpattern-v3`, consumed read-only through three explicit contracts (section 7); its production scripts are never modified
- **Companion site:** `../mindpattern-rabbit-hole`
- **Pilot horizon:** up to four campaign attempts, intended for manual public release after approval, no more than one per week
- **Supersedes:** `2026-07-10-agentic-media-campaign-harness-spec.md`, which was rejected on 2026-07-11
- **Deferred design:** `2026-07-11-campaignos-deferred-architecture.md`

This revision deliberately tests the editorial product before building a media-company control plane. It preserves v1's strongest safety mechanisms—source locking, exact-hash approval, explicit publication attempts, `UNCERTAIN` slot blocking, trustworthy nulls, and model/tool isolation—but removes infrastructure and process that a single operator cannot justify or staff.

## Evidence legend

- **Confirmed:** directly observed in repository code, tests, configuration, logs, or Git history.
- **External:** supported by the linked current first-party source.
- **Inference:** a reasoned conclusion from confirmed or external evidence; not yet proven.
- **Proposed:** behavior this specification asks the owner to approve.
- **Unknown:** needs account access, a real pilot result, or an owner decision.

## Review checkpoint

- [x] Rechecked the model, orchestration, story/evidence, audio, video, email, social, approval, receipt, deployment, and test paths.
- [x] Reconciled every fatal and major finding in the 2026-07-11 owner-supplied adversarial review.
- [x] Rechecked current first-party pricing and platform constraints; historical X tier pricing was not reused.
- [x] Reduced the operating model to one owner, one review action over exact core/leaf hashes, one local runtime, and four campaigns.
- [x] Added explicit bootstrap paths for evidence, similarity, and episode-specific visuals.
- [x] Added labor, cash, pause, pivot, scale, and program-kill rules.
- [x] Completed fresh-context adversarial review: initial verdict `REVISE`; reconciled all repository/general blockers; final narrow re-audit found no remaining specification blocker.
- [x] Reconciled the 2026-07-12 second adversarial review: pilot-total cash cap arithmetic, scorecard/attribution consistency, same-date slug ambiguity, YouTube submit-window semantics, caption-timing source, stale auth blocker, and `_clean()` attribution.
- [x] Owner directed on 2026-07-12 that CampaignOS is a standalone project. Runtime, lease, structure, commands, tests, and budget sections revised: mindpattern-v3 is consumed through three explicit contracts and its production scripts are not modified.
- [x] Owner resolved the decisions and approved this specification on 2026-07-12 ("i approve", working session). Decisions 1–5 and 7–9 recorded as written; Decision 6 (account identities, communities, watchlist) remains open and is due before campaign 1 launch.
- [x] Phase 2 implementation plan and dependency-ordered task list: `2026-07-12-campaignos-phase2-plan.md` (pending its own approval before any code).

## 1. Executive decision

Build a **local campaign compiler and operator cockpit**, not an autonomous social bot and not a cloud control plane. It is a standalone project in its own repository; mindpattern-v3 remains the content source, reached through three narrow contracts, and a pilot bug in CampaignOS cannot touch the daily research pipeline.

For four campaigns, the system will turn one already-published, source-backed MindPattern story into:

- one 4–7 minute source-grounded Field Note that works as both video and audio;
- one MP3, transcript, captions, source notes, and podcast-ready episode package;
- one 16:9 evidence-card video and, from campaign 2 onward, one complete 20–60 second Short;
- one approved package each for X and Bluesky, plus a Reddit package only when a real community need and current rules justify it;
- one compact opportunity brief that helps Tayler participate in relevant conversations without automating likes, follows, replies, comments, DMs, or votes;
- one aggregate outcome and labor/cost retrospective.

All public publishing and all conversational engagement remain manual during the pilot. Agents automate research packaging, evidence mapping, drafting, revision, rendering instructions, checks, opportunity triage, and retrospective proposals. Python owns state and permissions. Tayler owns editorial judgment, final approval, publishing, and every reply.

### The riskiest hypothesis

> A person who does not already follow MindPattern will find a disclosed AI-narrated, source-grounded Field Note useful enough to consume meaningfully or take a high-intent action.

Examples of high-intent action are a substantive reply/comment, source click, return visit, or tagged subscription-form success (with new-contact status reported separately when actually known). Four campaigns cannot prove a growth strategy statistically. They can determine whether the media product is credible, whether any audience signal appears, and whether one person can operate it at a sustainable cost.

The pilot cannot privacy-safely join an individual action to that person's follower history. It therefore tests two directional conditions separately: (a) a platform reports meaningful new-viewer/non-follower reach, and (b) the campaign receives external high-intent signals. Both must pass before `SCALE`; the report must not claim they came from the same people.

### The decision after campaign 4

There are only three outcomes:

1. **Scale:** the product, safety, labor, and audience-signal gates pass; plan one narrowly justified automation or distribution investment.
2. **Pivot:** quality is credible but exposure or audience response is insufficient; change the editorial format or distribution practice without buying scale infrastructure.
3. **Stop:** the format is not credible, is unsafe, is too expensive, or consumes too much owner time.

“Keep building the platform because the data is inconclusive” is not an allowed default.

## 2. Objectives and non-objectives

### Objectives

1. Produce four trustworthy campaign bundles from real MindPattern stories.
2. Make each bundle useful to a person who encounters it without already following the account.
3. Reduce active human work while preserving one informed final review.
4. Exercise crash recovery and duplicate prevention without managed infrastructure.
5. Establish honest baselines for quality, operator minutes, cash, render time, exposure, consumption, and high-intent response.
6. Learn whether audio/video merits continued investment before automating RSS, uploads, social writes, or self-improvement.

### Explicit non-objectives

- paid Anthropic API, Anthropic SDK, a generic model gateway, token-dollar reservations, or cloud sharing of a subscription session;
- Temporal, managed PostgreSQL, R2, a cloud render worker, Kubernetes, or a second workflow runtime;
- automatic X, Bluesky, Reddit, YouTube, podcast, or email publishing;
- automatic replies, comments, likes, follows, votes, reposts, DMs, mentions, or moderator/collaborator outreach;
- LinkedIn generation, publishing, or engagement;
- a privacy identity vault, pseudonymous cross-device joins, multi-arm experiments, L3/L4 promotion, or self-modifying prompts/code;
- two-human agreement metrics, blinded human raters, named backup roles, or 24/7 incident staffing;
- a podcast-directory launch before the audio product passes its staged gate;
- replacing the daily research/newsletter pipeline or implementing unrelated recommendations from `docs/ai-pipeline-evaluation.md`.

## 3. Confirmed current state

| Area | Evidence | Consequence for v2 |
|---|---|---|
| Daily state machine | `orchestrator/pipeline.py:Phase` defines `INIT -> TREND_SCAN -> RESEARCH -> SYNTHESIS -> DELIVER -> SITE_CONTENT -> LEARN -> SOCIAL -> ENGAGEMENT -> IDENTITY -> MIRROR -> SYNC -> COMPLETED`; Python owns transitions. | CampaignOS remains a separate, operator-started local workflow. `INIT` is included correctly. |
| Scheduled machine | `deploy/com.mindpattern.pipeline.plist` runs the Mac job hourly from 07:00–11:00; `run-launchd.sh` defaults `MP_LAUNCHD_SKIP_SOCIAL=1`. | Pilot work may use the same Mac only outside the protected daily window and while no daily pipeline process is active. |
| Model boundary | `docs/spec-research-reliability.md`, `orchestrator/agents.py:run_single_agent`, `core/llm.py`, and `core/claude_cli.py` explicitly use local `claude -p` under Tayler's subscription and reject paid API migration. | All campaign language-model work stays local through the existing CLI boundary. No token-price budget exists. |
| Public story seed | `orchestrator/site_content.py:is_publishable_site_story` requires sources and nonempty `claim_evidence`. | A published story is necessary but not sufficient for media adaptation. |
| Evidence granularity | `orchestrator/site_content_engine.py:_claim_evidence_candidates` normally creates one claim from the primary summary and first source. | The pilot creates a small campaign claim set and rejects unsuitable stories; it does not attempt to atomize an unlimited article. |
| Audio | `orchestrator/audio_briefing.py:build_audio_script` is deterministic; `build_tts_audio` is dry-run unless a provider is injected. Current artifacts/routes are date-keyed morning briefings, and `orchestrator/sync.py` does not sync campaign/audio binaries. | Reuse safe contract/redaction ideas only. The current site surface cannot host stable campaign episodes without a new route/storage/sync contract, which is excluded from v2. |
| Video | `orchestrator/video_scripts.py` explicitly creates offline 30/45/60-second packages and calls no renderer, provider, social API, or uploader. | Build a new deterministic local render path; do not pretend an uploader exists. |
| Email | `orchestrator/newsletter.py` and `orchestrator/runner.py` already deliver and broadcast through Resend with date-scoped receipts during the morning pipeline. | Keep it independent and list its allocated cost. Campaign work starts after delivery, so v2 does not insert a block or send a second email. |
| Approval | `social/approval.py:ApprovalGateway` accepts only explicit owner tokens and fails closed when owner identity is absent. | Preserve owner-only approval, but use one review action over exact core/leaf hashes rather than approximately ten review sessions. |
| Receipts | `core/receipts.py` claims one-bit receipts before external actions and exposes `MP_DISABLE_OUTBOUND=1`. | Preserve the kill switch; add a pilot-local attempt ledger for truthful manual outcomes and `UNCERTAIN`. |
| Deployment | `fly.toml` runs the API and Slack bot on one 2-CPU/2-GB Fly machine. | No campaign generation or rendering runs on Fly in the pilot. |
| Local renderer | `ffmpeg` was not installed when checked on 2026-07-11; macOS `say` and `claude` were available. | FFmpeg installation is an explicit owner decision. System TTS is rehearsal-only; public TTS needs an approved voice/provider. |

### What is inferred, not confirmed

- The Mac is probably adequate for one weekly evidence-card render, but actual render time, heat, and interference must be measured.
- A 4–7 minute Field Note is probably more feasible than v1's 8–15 minute episode, but pilot quality and retention will decide.
- Existing stories likely vary widely in campaign readiness. No claim is made that the newest or highest-ranked story will pass the new evidence gate.
- Follower-independent discovery on X, Reddit, Bluesky, search, and YouTube makes cold-start distribution possible, not guaranteed.

## 4. One-person operating contract

There is one accountable human role: **owner/editor/publisher/community operator**. Model “roles” are bounded software workers, not employees and not incident owners.

### Human work budget

| Activity | Campaign 1 allowance | Recurring target |
|---|---:|---:|
| Select story and angle | 15 min | 15 min |
| Review/repair claim set | 45 min | 45 min |
| One combined bundle review and approval | 45 min | 45 min |
| One consolidated revision contingency | 30 min | 30 min |
| Manual uploads/posts and receipt confirmation | 20 min | 20 min |
| Three community sessions, including replies | 45 min | 45 min |
| Metrics and retrospective | 15 min | 15 min |
| First-use voice/template/account setup | 145 min | 0 min |
| **Active-human allowance/target** | **6 hours** | **3 hours 35 min** |

The rows now sum to the displayed totals. The harness records active minutes by activity. Waiting for Claude, TTS, and rendering is tracked separately and is not disguised as editorial labor. Campaign 1 may use six active owner hours, campaign 2 five, and campaigns 3–4 four each. Those are stop ceilings, not promises that the work should expand to fill them.

### One-time implementation budget is separate

The weekly table does not hide the cost of building the harness. Before any code, Phase 2 must estimate one-time engineering execution, owner review/decision time, dependency setup, private rehearsal, and companion-site/backend work. The recommended provisional ceiling is **80 engineering hours plus 12 active owner-review hours** before the first public campaign. Actual time is recorded and shown both separately and amortized across the four-campaign result.

If the Phase 2 estimate exceeds either ceiling, the plan must remove scope or return for a new owner decision before implementation. If actual work reaches a ceiling before the private rehearsal passes, implementation pauses; sunk work is not permission to continue.

### Availability and incidents

- There is no on-call rotation and no named-backup gate.
- If Tayler is unavailable, the campaign pauses. Nothing “uses best judgment” to publish or respond.
- Public launches occur only when Tayler can check the affected accounts during one declared operating window that day and the next business day.
- A suspected unsupported claim, rights problem, secret/PII leak, or platform warning immediately pauses new exports. Tayler uses native controls to unlist/delete/correct as soon as practical during operating hours, then records the outcome.
- The pilot makes no four-hour correction or 60-minute incident-response promise. The internal target is acknowledgement by the next operating session and a decision within one business day.

### Single review, not duplicated ceremony

The final review is one session:

1. Read the claim map and disclosure summary.
2. Watch the complete 4–7 minute video once.
3. Replay one deterministic 60–90 second segment audio-only to catch visual-dependent narration.
4. Skim the transcript, source notes, thumbnail, channel copy, and destination preview.
5. Approve the exact core and current leaf hashes in one action, reject them, or request one revision.

The review records five 1–5 scores: evidence fidelity, usefulness to the target decision, audio/visual clarity, distinctiveness, and trust/voice. Evidence fidelity and usefulness must each be at least 4, and no score may be below 3. Scores are one owner's repeatable decision record, not inter-rater statistics.

This replaces separate full watch, full listen, full read, independent council, and per-asset approvals. The ceiling is 45 minutes and the target is 30 minutes after campaign 1.

## 5. Campaign product and sequence

### Common bundle for every campaign

- `ClaimSet`: 3–7 consequential claims, their evidence, confidence, and permitted uses.
- `FieldNoteScript`: 600–1,000 spoken words, 4–7 minutes, written to make sense without visuals.
- `AudioMaster`: local MP3 plus transcript, chapters, show notes, disclosure, source list, and a stable ID inside the campaign bundle.
- `LongVideo`: 1920x1080 evidence-card video using the same approved narration.
- `Short`: from campaign 2 onward, one complete 20–60 second derivative that makes a supported point.
- `Thumbnail`: one deterministic template with episode-specific title/art/source motif.
- `ChannelPack`: one complete native-value X post, one Bluesky post, optional Reddit text, tracked destination, and disclosures.
- `OpportunityBrief`: no more than three relevant conversations/communities, why they fit, source context, and a suggested contribution angle—not an auto-postable impersonation reply.
- `OutcomeCard`: costs, active minutes, render/model/provider attempts, aggregate metrics, incidents, audience signals, and next hypothesis.

### Staged campaign sequence

| Campaign | Product increment | Distribution increment | Gate to continue |
|---|---|---|---|
| 1 — credibility | Long video, local MP3, transcript, sources, thumbnail, X/Bluesky packs | Manual YouTube upload; the same narration is reviewed as local audio but has no separate public audio host; one or two manual originals | Evidence fidelity/usefulness >=4/5, no review score <3, zero unsupported claims/critical defects, active time <=6h |
| 2 — repeatability | Same bundle plus one complete Short | Repeat campaign 1; no campaign-site audio or RSS host yet | Two reproducible bundles; no duplicate/receipt ambiguity; active time <=5h or stop/simplify |
| 3 — audio/discovery | Same; refine audio from observed issues | Owner may add Transistor by manual upload only if campaigns 1–2 audio passed and Decision 5 approves it; community participation expands only where authentic | No rights/policy incident; audio value is credible; cash remains under cap |
| 4 — operating proof | Same bundle, no new infrastructure | Optional manual Reddit post only after comment-first participation, current community rules, and a real question the campaign answers | Run the final scale/pivot/stop scorecard |

Skipping a distribution increment is truthful. It does not fail the campaign if the required account, permission, community fit, or owner availability is missing. The status records `NOT_ATTEMPTED` with a reason; missing is never reported as zero performance.

The pilot may inspect at most six story seeds and run for at most six calendar weeks to produce its four campaign attempts. Every rejected seed and its owner minutes count toward operability. Rejected-seed minutes are recorded in the pilot operability record and retrospective; only the accepted seed's selection and evidence minutes count against that campaign's active-hour ceiling. Failure to find four acceptable seeds inside either limit is a pilot failure, not permission for endless reselection.

Medical, legal, personalized financial, active exploitation/security, unverified allegations about identifiable people, and uncertain-rights stories are excluded from this one-generalist pilot.

### Cold-start distribution loop

The operating strategy is:

`useful native contribution -> conversation -> profile trust -> source-rich MindPattern page -> email subscription`

- Give the core answer natively. The link is a deeper evidence trail, not a withheld payoff.
- X: publish a concise finding plus caveat/question, then Tayler makes a small number of substantive manual contributions in existing relevant conversations.
- Bluesky: use legitimate topical feeds/search conventions, converse with researchers, and avoid mass-follow or starter-pack manipulation.
- Reddit: listen and comment before posting; write for a specific community question; check current rules; use no API publisher and no promotional bot.
- Answer every serious response that merits an answer, manually and within the declared community-time budget. Silence is acceptable when no useful response is possible.

The harness may rank opportunities and prepare source context. It cannot expose a follow/like/vote/DM/reply/comment method during this pilot.

## 6. Bootstrap gates that work on campaign 1

### 6.1 Evidence lock

A campaign may use **3–7 consequential claims**, not every sentence in the source story. A claim is consequential if it includes a number, date, quote, named-entity action, capability, causal statement, prediction, legal/safety/security/privacy/financial assertion, or a proposition necessary to the thesis.

Each claim record contains:

- stable `claim_id`;
- one atomic claim in plain language;
- exact source URL and source title;
- a short supporting excerpt or structured evidence note;
- source publication/access date when available;
- evidence role (`supports`, `qualifies`, `contradicts`, or `context`);
- confidence and explicit uncertainty;
- allowed asset uses;
- reviewer status and reason.

Every factual script/visual/social segment carries one or more claim IDs. `analysis`, `opinion`, and `transition` segments may have none, but cannot introduce a new entity action, number, date, capability, or causal assertion.

**Bootstrap rule:** the Evidence Editor gets at most two model attempts and Tayler gets at most 45 active minutes to approve or repair the claim set. If any selected claim remains unsupported, or the story cannot yield three useful supported claims, the candidate becomes `REJECTED_EVIDENCE` and the operator selects another published story. The campaign never waits indefinitely in `EVIDENCE_LOCK`.

The existing `is_publishable_site_story()` result is an eligibility input, not evidence-lock approval.

#### Source-pack acquisition

Evidence lock uses the snapshotted published story revision, stored finding/report artifacts, and source metadata already present locally. If they are insufficient, Tayler may open a referenced source in an ordinary browser and manually import a bounded excerpt or local file. The import records source URL, access time, local content hash, excerpt, and who supplied it; imported text remains untrusted model data.

The pilot harness performs **no network source fetch**. It has no URL fetcher, browser tool, cookies, login, proxy, paywall bypass, or model-selected host. This removes an otherwise unnecessary SSRF and source-access subsystem. At most six source documents may enter one campaign pack. An inaccessible or ambiguous source causes the claim to be removed or the seed to be rejected.

Any future automated retriever requires a separate security contract covering schemes, credentials-in-URL, ports, public IP/DNS validation, IPv4/IPv6 private/link-local/metadata ranges, redirects, DNS rebinding, proxies, content type/size, timeouts, decompression, parser isolation, access terms, and adversarial fixtures.

#### Exact story-revision identity

Current story files can be replaced at the same date/slug, and the public slug lookup does not expose a revision identity. “Exact story revision” is therefore a new contract, not a confirmed repository feature.

At seed time the runner:

1. resolves one validated `reports/<user>/site-stories/<date>/<slug>.json` path;
2. rejects a slug whose file lookup resolves to more than one candidate file — across archive dates or within one date; same-date bare-slug and date-prefixed variants with differing content were observed in `reports/ramsay/site-stories/2026-07-12/` on 2026-07-12 — until the ambiguity is resolved, and the revision-hash API must apply the same deterministic resolution rule as the public slug route;
3. copies the exact raw bytes into the immutable campaign input directory;
4. records `story_revision_sha256 = SHA256(raw_bytes)`, original path, date, slug, and seed time; and
5. deduplicates campaign seeds on that full hash, not slug/date alone.

The minimal API/source contract must expose the SHA-256 of the raw story file selected for `/s/<slug>` (without rewriting the file). Destination validation compares that remote hash, date, and slug with the approved snapshot immediately before approval and again before every channel export. A mismatch invalidates the core and blocks the link. Post-launch revision changes are recorded as destination/correction events; the system does not pretend a mutable URL permanently pins bytes.

### 6.2 Similarity and originality

Campaigns 1–4 have no fixture-calibrated semantic threshold because no accepted/rejected corpus exists.

They use:

- exact full-file and normalized-text duplicate hard failures;
- repeated-title, repeated-opening, and repeated-scene-sequence warnings;
- a recorded owner rubric for `distinct thesis`, `new evidence`, `new consequence`, and `non-formulaic narration`, each scored 1–5;
- a minimum score of 4 for distinct thesis and no score below 3;
- retained accepted, rejected, and revised bundles as future fixtures.

No numeric semantic-similarity policy may become a publication gate until a later spec identifies an adequate labeled corpus and validates the threshold. The owner cannot merely write “different enough”; the four rubric scores and a one-sentence rationale are required.

### 6.3 Episode-specific visuals

The pilot target is achievable and measurable:

- at least three story-specific, evidence-bearing scenes;
- episode-specific treatment totaling at least the lesser of 90 seconds or 25% of runtime;
- at least one source/evidence treatment, one original comparison/timeline/diagram, and one limitation/uncertainty/counterpoint treatment;
- every evidence scene links to claim IDs and source provenance;
- generic brand backgrounds, captions, transitions, and waveform treatment are allowed for the remaining runtime;
- generated or stock atmosphere never counts as evidence and is unnecessary for the pilot.

If this treatment takes more than 45 active human minutes for two campaigns, the pilot records a product/renderer failure and simplifies the format before continuing. It does not silently waive the rule.

### 6.4 Audio comprehension and accessibility

- The script must communicate the thesis and evidence without “as you can see” dependencies.
- Essential visual comparisons are narrated; decorative detail need not be.
- Captions cover all narration and have no negative, overlapping, or out-of-range timestamps.
- Transcript, source notes, and disclosure ship with the audio/video package.
- A fixed 60–90 second audio-only sample is part of the single final review; automated text checks scan the whole script for visual-only references.

## 7. Local target architecture

```mermaid
flowchart LR
    A[Published MindPattern story] --> B[Local campaign runner on Mac]
    B --> C[Campaign + Evidence Editor<br/>claude CLI, no tools]
    C --> D[Locked 3-7 claim set]
    D --> E[Script and Channel Studio<br/>claude CLI, no tools]
    E --> F[Deterministic validators]
    F -->|repair, max one cycle| E
    F --> G[Local TTS adapter + FFmpeg renderer]
    G --> H[Immutable bundle + SHA-256 root]
    H --> I[Tayler single review/approval]
    I --> J[Manual exports/uploads/posts]
    J --> K[Attempt receipts + aggregate metrics]
    K --> L[Retrospective proposal]
```

### Runtime choice

The pilot has exactly one runtime: a local Python runner on the Mac, living in the standalone `campaignos` repository, with SQLite state and immutable files. It is single-writer and permits only one active campaign build. There is no `WorkflowRuntime` abstraction.

- A pilot-only `<campaignos>/data/pilot.db`, excluded from Git, owns campaign state, approvals, attempts, costs, minutes, and metric imports. Its schema still requires explicit implementation approval.
- `<campaignos>/artifacts/<campaign_id>/` owns immutable input, intermediate, render, export, and evaluation artifacts.
- Atomic file replacement and SQLite transactions protect commits.
- CampaignOS holds its **own atomic lock** (`mkdir`-style with token/PID/start metadata and race-tested stale recovery) for the duration of a build. It never mutates the mindpattern-v3 repository, so no shared Git-level lease exists or is needed.
- Before acquiring its lock and again before every model or render stage, CampaignOS runs a **read-only conservative busy check** against mindpattern's documented local lock paths (the pipeline `mkdir` directory lock, the pipeline flock file, and the harness lock) and refuses to start or proceed while any appears held. mindpattern-v3's `run-launchd.sh`, `run.py`, `harness/run.sh`, and Slack bot are **not modified**. The residual start-after-check race is bounded by the time-window prohibition below and by treating Claude subscription contention as `BLOCKED_MODEL_CAPACITY`, never a retry storm.
- Repository evidence confirms mindpattern's own lock mechanisms are fragmented (an atomic `mkdir` directory lock, a `flock` on a different file, a check-then-act harness guard, and a bot mutex that is defined but never called). Unifying them is mindpattern-v3's own backlog item, not a CampaignOS deliverable; CampaignOS only has to lose conservatively to all of them.
- Re-running resumes the next incomplete deterministic step; it never silently starts a second campaign.
- Campaign work is prohibited from 06:45–13:00 local time even if every lock appears free.
- Tayler does not invoke model-backed Slack commands while a campaign build runs. The deployed Fly bot is a separate machine and cannot share a filesystem lock; unexpected subscription contention becomes `BLOCKED_MODEL_CAPACITY`, not an automatic retry storm or a false global-capacity guarantee.
- Fly and Vercel are read/delivery surfaces only; they do not orchestrate or render.

CampaignOS consumes mindpattern-v3 through exactly three contracts:

1. **Story input (read-only):** a configured `MINDPATTERN_REPORTS_DIR` path for snapshotting the exact raw story bytes, plus the new dashboard endpoint exposing the SHA-256 of the story file served for `/s/<slug>`. That endpoint is implemented in mindpattern-v3 and, besides the analytics extension, is that repo's only pilot code change.
2. **Busy/lock convention:** the read-only conservative check above against mindpattern's documented lock paths, plus the shared time-window prohibition.
3. **Attribution aggregates:** the separately approved section-11 analytics extension; CampaignOS imports aggregate counts only.

The deferred appendix defines evidence that could justify a managed runtime. At that point the owner must choose **one** runtime in an ADR. Reimplementing Temporal semantics on PostgreSQL is not an acceptable fallback requirement.

### Model boundary and capacity accounting

- Every language-model call invokes the existing local `claude` CLI under Tayler's subscription.
- Paid Anthropic API/SDK keys are prohibited. No cloud worker may assume it can share the local subscription session.
- The only permitted model credential is the Claude subscription/OAuth authentication required by the CLI. `claude auth status --json` or an equivalent non-secret preflight must prove an approved subscription mode; `none`, unknown, paid API-key, Bedrock, Vertex, or Foundry mode blocks the campaign. The 2026-07-11 interactive audit reported `loggedIn: false`; a 2026-07-12 recheck reported `loggedIn: true` on a Max subscription, so the preflight currently passes. It remains a hard launch gate because shell auth state can change.
- The child environment is built from a minimal allowlist and strips `ANTHROPIC_API_KEY`, third-party model/provider flags, cloud credentials, Slack/social/email/TTS keys, application secrets, hooks, and campaign-external state. It may pass only the approved Claude subscription auth context plus basic process locale/path/temp values. Secrets are never logged.
- The current CLI must run with customization/tool isolation equivalent to `--safe-mode --tools "" --disable-slash-commands --strict-mcp-config --mcp-config '{"mcpServers":{}}' --no-chrome --no-session-persistence --json-schema ...`. Version/flag support is preflighted. The prompt enters on stdin, not the process list, and the working directory is an empty campaign scratch directory rather than the repository.
- Model subprocesses receive no built-in tools, skills, hooks, plugins, MCP servers, publishing adapters, database handles, or writable campaign state. Admin-enforced settings or any configuration that reintroduces authority cause preflight failure.
- Prompts delimit story/source/platform text as untrusted data. External text cannot change instructions, permissions, tools, policy, or output paths.
- Outputs must pass strict typed-schema, string-length, URL-host/scheme, claim-ID, and path validation before use.
- Every call records role, prompt/version hash, model label, safe-mode/tool/auth-mode preflight result, start/end time, attempt, exit/classification, and output hash—never the credential or full sensitive prompt.
- Capacity is controlled by **calls, attempts, wall time, and subscription errors**, not invented token-dollar reservations.
- Maximum path: campaign/evidence draft, optional evidence repair, script/channel draft, critic, optional consolidated repair, critic recheck, and retrospective = **seven successful stage calls**. The hard cap is ten total process attempts, one consolidated editorial repair, and 60 minutes of cumulative model wall time per campaign.
- Usage-limit or repeated-overload exhaustion produces `BLOCKED_MODEL_CAPACITY`; it pauses until a later operator session and never falls back to a paid API or cheaper unapproved provider.

### Bounded model roles

| Role | May do | May not do |
|---|---|---|
| Campaign and Evidence Editor | propose the bounded angle/audience job, then atomize/map up to seven claims and flag gaps | invent evidence, browse, select tools, publish, waive a missing source, or approve itself |
| Script and Channel Studio | draft structured script segments, scene plan, titles, description, and native copy from locked claims | introduce unlocked facts or call providers/platforms |
| Adversarial Critic | return typed defects against evidence, clarity, voice, policy, and accessibility rubrics | edit artifacts, lower gates, or approve |
| Retrospective Analyst | summarize aggregate outcomes and propose the next human-reviewable hypothesis | claim causality, promote a prompt, mutate code/config, or increase authority |

The Critic is independent in context and prompt, not an independent human rater. There is no Cohen's kappa requirement.

## 8. State, approvals, and publication truth

### Campaign state

```text
SEEDED
  -> EVIDENCE_LOCK
  -> DRAFTING
  -> VALIDATING
  -> RENDERING
  -> OWNER_REVIEW
  -> APPROVED
  -> EXPORT_READY
  -> MEASURING
  -> CLOSED
```

Terminal/side states are `REJECTED_EVIDENCE`, `REJECTED_EDITORIAL`, `BLOCKED_MODEL_CAPACITY`, `BLOCKED_PROVIDER`, `PAUSED`, and `CANCELLED`. State transitions are explicit Python commands with expected-version checks. Models return proposals only.

### One review action with exact core and leaf approvals

The release manifest contains a `core_content_hash` over the claim set, script, master narration, source manifest, disclosures, and CTA. It also contains exact leaf hashes for video, audio, the Short, and each channel package. The manifest's own SHA-256 is the complete audit root.

- Tayler reviews and approves the core plus every current leaf in one action.
- A core change invalidates every dependent approval.
- A leaf-only change invalidates only that leaf and receives a focused re-review; it does not force Tayler to rewatch unchanged media.
- Destination account and an approved publication window are hashed; a routine delay inside that window does not invalidate unchanged content.
- Deterministic export wrappers may add platform-required packaging metadata only when that metadata is already represented in the approved manifest.
- **No native edit exception exists.** Any owner change after approval—including punctuation, whitespace, typo, number, date, URL, disclosure, or scheduling text—creates a new exact leaf, cancels the current `READY/SENDING` attempt before submission, reruns deterministic validation, and receives focused owner reapproval. If edited content is posted first, it is recorded `POSTED_UNAPPROVED_VARIANT`, the channel pauses, and Tayler decides whether to correct/remove it.
- Platform transcoding/link-preview changes are verified through platform IDs and status; public bytes are not falsely expected to equal local media bytes.
- Public-release approval uses the same Slack owner-allowlist mechanism mindpattern already proves out (Mac-local Web API post-and-poll with the Keychain bot token and owner user ID), reimplemented inside CampaignOS with the durable lifecycle below: the request displays the exact core/leaf/audit hashes, and only the configured owner ID can approve. SQLite stores that owner ID, Slack message/thread ID, timestamp, and hashes. If Slack or owner identity is unavailable, public approval fails closed.
- A local CLI review may mark a private fixture `REHEARSAL_REVIEWED`; it cannot create a public `APPROVED` record. There is no unauthenticated `--owner tayler` shortcut.

The current `ApprovalGateway` keeps its thread ID in memory and is not sufficient by itself. Pilot approval adds a durable request lifecycle:

```text
READY -> SENDING -> AWAITING_OWNER -> APPROVED | REJECTED | EXPIRED
                  -> UNCERTAIN_APPROVAL_REQUEST -> AWAITING_OWNER | ABANDONED
```

Before posting to Slack, SQLite commits the exact hashes, owner ID, expiry, and a unique non-secret request nonce. The Slack message includes that nonce. Success persists channel/message/thread IDs. A timeout, connection loss, or crash after `SENDING` becomes `UNCERTAIN_APPROVAL_REQUEST`; it cannot repost until Slack history or Tayler reconciles the nonce. Owner replies are ingested idempotently by message/reply ID and must reference the still-current request. A stale or duplicate approval cannot authorize a new hash.

This is a small hierarchical hash manifest, not a distributed Merkle service and not ten separate approval sessions.

### Publication attempt lifecycle

Each logical `(campaign_id, channel, format)` slot has at most one unresolved attempt:

```text
NOT_ATTEMPTED -> READY -> SENDING -> CONFIRMED
                         |       -> DEFINITELY_NOT_SENT -> READY
                         |       -> UNCERTAIN -> CONFIRMED | ABANDONED
                         -> CANCELLED
```

The manual flow is:

1. Export the exact approved platform package.
2. Run `attempt start` immediately before using the native publish control. It atomically binds the current approved leaf, rechecks the local and remote destination story revision, and issues a five-minute manual-submit window.
3. Publish manually.
4. Run `attempt confirm --url ...`, `attempt definitely-not-sent`, or `attempt uncertain`.

`UNCERTAIN` blocks another create for that slot until Tayler finds the native post or explicitly abandons it with a reason. A timeout, lost browser confirmation, or unclear native result is never assumed to mean “not sent.” Package hashes prevent an old draft from being mistaken for the current bundle.

If the destination hash changed or cannot be verified, `attempt start` fails before `SENDING`. If Tayler does not submit inside the five-minute window, the untouched attempt is cancelled/revalidated; if submission may have occurred, it becomes `UNCERTAIN`. This narrows but does not misrepresent the unavoidable manual UI gap. For YouTube, the window covers only the final visibility/publish action; uploading and processing a private draft may begin before `attempt start`, since a long upload cannot fit a five-minute window.

There is no live platform write method in pilot code, so the five-second automatic network-block claim from v1 is deleted. `MP_DISABLE_OUTBOUND=1` remains the intended central fail-closed boundary, but repository review confirmed that current `audio_briefing.build_tts_audio()` does **not** check it. Before any live TTS adapter exists, that gap must be fixed and tested so the switch is checked before configuration/credential resolution and the provider call. A local pause flag is checked before every new campaign/provider/export step.

## 9. Media implementation boundary

### Build for the pilot

- Extend the existing media contracts rather than replacing their safe path/redaction behavior.
- Add a provider-neutral TTS adapter with a fake test provider, macOS rehearsal provider, and one explicitly enabled public provider after owner approval.
- Add deterministic Pillow evidence-card/thumbnail rendering and FFmpeg composition for MP3/video/captions.
- Use the same narration, script hash, claim IDs, and source notes for audio and video.
- Caption timestamps must come from a deterministic source specified in Phase 2 — per-segment TTS synthesis with measured durations, or a separately approved forced-alignment dependency. No timing source is assumed to exist in the current dependency set.
- Produce YouTube-ready files and podcast-ready metadata; upload manually only to an explicitly approved destination.
- Keep large binaries local and, after approval, on YouTube or the optional podcast provider. Do not add a campaign site-media path or R2 for four campaigns.

### Do not build for the pilot

- Remotion, cloud rendering, provider polling queues, YouTube OAuth, podcast-host API, automatic RSS mutation, a new campaign-audio site route/sync path, X write API, or Reddit publisher;
- generated B-roll, realistic synthetic people, voice imitation without verified rights, or third-party voice cloning;
- a second long-video cut, three Shorts, dynamic ad insertion, or auto-generated fake host conversation.

### Billable TTS attempt truth

Public TTS is the pilot's only new billable generation call. It uses a stable slot keyed by campaign, approved script hash, provider, model, voice, and settings. Before the call, the system records the provider's estimate, remaining pilot cap, request fingerprint, and `SENDING`. Success records provider request ID, measured characters/credits/cash when available, and audio hash.

A timeout, connection loss, or crash after `SENDING` becomes `UNCERTAIN_PROVIDER`. The system does not blindly regenerate and spend again. Tayler inspects provider history or explicitly abandons the attempt before another paid call. Deterministic local encoding/render repairs are not billable TTS attempts and may reuse the approved audio bytes.

Calling the injected provider while `MP_DISABLE_OUTBOUND=1` is a release-blocking test failure. Dry-run metadata generation remains allowed because it makes no network request and spends nothing.

### Deterministic media gates

Before owner review:

1. Every consequential segment resolves to an approved claim ID.
2. Exact quotes match evidence and attribution is audible/visible.
3. Narration text matches the approved script outside a recorded pronunciation map.
4. Audio duration, codec, sample rate, clipping, long silence, and loudness are measured; public target is approximately -16 LKFS with true peak no higher than -1 dBFS.
5. Video resolution, duration, frame rate, audio stream, blank-frame samples, safe areas, and caption coverage pass.
6. At least three evidence scenes and the lesser of 90 seconds or 25% story-specific runtime pass lineage checks.
7. Every asset has a rights/provenance status; unknown rights fail.
8. AI narration and any synthetic illustration are disclosed in the asset metadata/description.
9. Exact duplicate and owner originality rubric gates pass.
10. Destination, transcript, source notes, and correction contact preview correctly.

Automated checks reduce review load; they do not grade whether the story is worth a person's time.

## 10. Engagement and authenticity boundary

“Human-like” means relevant, specific, evidence-aware, and continuous in voice. It does **not** mean concealing automation or imitating a person at machine scale.

### The harness may automate

- monitoring approved public topics/watchlists;
- ranking a small opportunity queue;
- detecting an owned mention that needs attention;
- summarizing the conversation and relevant MindPattern evidence;
- proposing a response objective, caveat, or useful source;
- identifying likely duplication, promotional tone, missing disclosure, or community-rule conflicts;
- reminding Tayler about unanswered serious responses;
- recording manual outcomes and recurring questions.

### The harness may not automate

- sending the reply/comment/DM, liking, voting, following, reposting, tagging, or inviting;
- keyword-triggered unsolicited responses;
- creating fake accounts/personas or concealing that media is AI-assisted;
- repeating the same reply, manufacturing agreement, coordinating engagement, or evading moderation;
- Reddit posting without a current community-rule record and Tayler's manual action;
- using private messages or platform user content in a model without an approved data-handling rule.

For campaigns 1–4, opportunities come from an owner-maintained watchlist, owned mentions visible to Tayler, or manually supplied public URLs/text. A future read connector requires separate platform/data approval; inability to automate discovery does not authorize browser scripting.

## 11. Measurement and learning without fake statistical power

### Pilot scorecard

For each campaign, record what the platform actually exposes:

- **discovery:** impressions/views and non-follower percentage when available;
- **consumption:** YouTube watch time, average percentage viewed, retention checkpoints, Transistor/audio metrics only if the campaign-3 option is approved, and qualified site sessions;
- **resonance:** substantive replies/comments, shares/reposts, saves/bookmarks where available, and Reddit upvote/removal status;
- **relationship:** distinct people with a two-turn conversation or a later repeat interaction;
- **owned action:** source clicks, return visits, and tagged subscription-form successes. A form/API success is **not** labeled a new subscriber unless the provider response explicitly distinguishes create from already-existing contact without exporting identity; otherwise new-contact status remains null;
- **guardrails:** hides/mutes/blocks/reports, removals, corrections, unsubscribes, and account warnings;
- **economics:** active owner minutes, elapsed time, provider/model/render attempts, cash, and existing allocated service cost.

Metrics are imported manually or through existing first-party aggregates at 24 hours and 7 days; the final campaign-4 review may include mature 28-day data for earlier campaigns. Missing, unavailable, private, immature, or uncollected values remain `null` with a reason. They are never converted to zero.

### No measurement vault

The pilot uses campaign IDs, platform-native aggregates, privacy-safe first-party events, and platform-specific UTM tags. It stores no email, raw anonymous identifier, Resend contact export/join, cross-device join, signed rotating subject token, or pseudonymous identity vault in CampaignOS.

### Minimal first-party attribution change

**Confirmed gap:** the current `memory/events_db.py` schema stores event type, target, path, referrer domain, optional random `anon_id`, and value. `analytics.ts` does not preserve campaign tags (it sends only `location.pathname` and the referrer hostname), and the server-side `_clean()` in `memory/events_db.py` strips query strings. Current first-party events therefore cannot support the campaign joins assumed above.

The pilot includes one deliberately small cross-repository change, subject to separate implementation approval:

- add validated `campaign_id` and `source_channel` fields to `site_events.db` and its event contract;
- on an allowlisted MindPattern landing URL, read standard `utm_campaign`/`utm_source`, normalize them to safe campaign/channel IDs, and retain them in **session storage only**;
- attach those fields to that browser session's permitted story, source-click, subscribe, and optional `share` events;
- expose a private aggregate grouped by campaign/channel/window; CampaignOS imports counts only;
- record `subscribe_success` only as a successful tagged form/provider request in that same session. It does not prove the contact was new; `new_contact_status` is null unless a non-identifying provider result explicitly supplies it;
- strip acquisition tags from internal/share URLs after capture and preserve the existing analytics opt-out.

No raw query string, email, IP, user agent, geo, cross-device identity, or new long-lived subject token is stored. If this minimal attribution is not implemented or fails validation, affected fields remain null and the pilot can only resolve to `PIVOT_UNTESTED_DISTRIBUTION`, never `SCALE_OPERABLE_SIGNAL`.

### No experiment winner

- One campaign is one case; its assets are not independent samples.
- Each campaign may pre-register one descriptive question, such as “does the opening explain the consequence sooner?”
- Dashboards label results `DESCRIPTIVE / HYPOTHESIS-GENERATING`.
- Tayler may make an editorial change after reading results, but the retrospective must state that the change is judgment, not a causal promotion.
- No prompt, model, rubric, policy, or strategy auto-promotes. The Retrospective Analyst writes a proposal only.

L3 experiments, L4 release engineering, holdouts, canaries, and privacy joins are deferred until the trigger conditions in the appendix exist.

## 12. Honest cost and capacity envelope

Prices below were checked against first-party pages on 2026-07-11. They exclude tax and can change. Account-specific bills and plan utilization were not accessed.

### Four-campaign pilot

| Cost | Required? | Current basis | Monthly planning amount |
|---|---|---|---:|
| Existing Anthropic subscription / Claude CLI | Yes | Existing owner subscription; exact plan allocation unknown. No per-token API billing or reservation. | existing allocated cost, **unknown** |
| Existing Resend | Existing, campaign-independent path | Official Free is 3,000 emails/month/100 daily and Pro is $20/month. Current plan/usage is unknown; v2 sends no campaign email. | existing allocated **$0 or $20+**, $0 planned campaign increment |
| Existing Mac | Yes | No new vendor; record active labor, elapsed render time, electricity, wear, and schedule interference separately. | no new vendor; economic cost tracked |
| One-time implementation | Yes before pilot | Phase 2 must estimate and cap engineering plus owner oversight; provisional ceiling is 80 engineering hours + 12 owner hours. | non-cash/economic cost, **not yet estimated** |
| FFmpeg | Proposed | No vendor fee; installation and license/build choice require owner approval. | $0 vendor |
| ElevenLabs Creator | Recommended for public TTS | Regular $22/month, 121k credits; official estimate about 121 TTS minutes. Four 4–7 minute masters plus limited repairs should fit, but actual characters/credits are measured. | **$22** |
| Transistor Starter | Optional after campaign-2 gate | $19/month; manual upload, RSS feed, and directory-ready hosting. | **+$19** if approved |
| YouTube manual upload | Yes for video | No API used; official docs expose quota rather than a per-upload cash fee. | $0 API |
| X/Bluesky/Reddit manual posting | Yes where eligible | No write API in pilot. | $0 API |
| R2, Temporal, managed PostgreSQL, cloud render | No | Explicitly deferred. | $0 |

**Incremental vendor cash:** approximately **$22/month** without a podcast host or **$41/month** with Transistor. This is not “total cost.” The approval view must also show one-time implementation/owner time, the existing Claude/Resend allocation, weekly owner minutes, Mac/render time, taxes, retries, and any account-specific purchase minimum.

The recommended pilot cash cap is **$85 before tax, cumulative across the full six-week pilot horizon**, excluding already-paid Claude and the current Resend plan. The cap is stated per-pilot, not per-month, because the six-week window can span two vendor billing cycles: up to two ElevenLabs cycles ($44) plus, if approved at campaign 3, up to two Transistor cycles ($38) totals $82. A pilot completed inside one billing month spends at most $41. A campaign-unrelated Resend upgrade remains visible in allocated cost but needs its own operating decision. No provider may auto-recharge.

### Costs deliberately avoided during the pilot

- Temporal Cloud Essentials is the greater of $100/month or 5% of consumption.
- Neon Launch is usage-based; its official example is about $15/month.
- X now publishes pay-per-use pricing rather than the reviewer-cited historical fixed ~$200 tier: ordinary post create is $0.015, a post with a URL is $0.200, and reads are separately metered. This could still create variable spend and policy/account work, so the pilot remains manual.
- Remotion is unnecessary because the pilot uses Pillow/FFmpeg. If reconsidered later, free commercial eligibility depends on organization/collaborator headcount; an automation license can introduce a $100/month minimum.

An illustrative managed-stack subtotal—Temporal $100 + Neon example $15 + Resend Pro $20 + ElevenLabs $22 + Transistor $19—is **$176/month before** X usage, render compute, object storage, tax, Claude subscription, and labor. It is included to prevent another misleading media-only headline, not to recommend that stack.

### First-party pricing/policy sources

- [X API pay-per-use pricing](https://docs.x.com/x-api/getting-started/pricing)
- [X automation rules](https://help.x.com/en/rules-and-policies/x-automation?lang=browser)
- [Temporal Cloud pricing](https://docs.temporal.io/cloud/pricing)
- [Neon pricing](https://neon.com/pricing)
- [Resend pricing](https://resend.com/pricing)
- [Resend quotas](https://resend.com/docs/knowledge-base/account-quotas-and-limits)
- [ElevenLabs pricing](https://elevenlabs.io/pricing)
- [ElevenLabs voice-cloning rights](https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning/instant-voice-cloning)
- [Transistor pricing](https://transistor.fm/pricing/)
- [YouTube Data API quota](https://developers.google.com/youtube/v3/getting-started#quota)
- [YouTube `videos.insert`](https://developers.google.com/youtube/v3/docs/videos/insert)
- [FFmpeg legal information](https://ffmpeg.org/legal.html)

## 13. Specified command interface

These commands describe the post-approval product contract. They do not exist yet and are not authorization to implement or run live providers. All commands run from the standalone `campaignos` repository's own venv; `MINDPATTERN_REPORTS_DIR` points at mindpattern-v3's `reports/` tree for read-only story input.

```bash
# Inspect eligible published stories; no model/provider call.
.venv/bin/python3 -m campaignos.cli candidates --user ramsay

# Create one local campaign from an exact story revision.
MP_DISABLE_OUTBOUND=1 .venv/bin/python3 -m campaignos.cli seed \
  --story-date YYYY-MM-DD --story-slug SLUG

# Build through validation with mocked/local providers; resume safely.
MP_DISABLE_OUTBOUND=1 .venv/bin/python3 -m campaignos.cli build \
  --campaign CAMPAIGN_ID --through owner-review

# Show defects, labor/cost ledger, hashes, and the single review checklist.
.venv/bin/python3 -m campaignos.cli review --campaign CAMPAIGN_ID

# Request an owner-only Slack decision over the exact core/current leaves.
.venv/bin/python3 -m campaignos.cli approval request \
  --campaign CAMPAIGN_ID --bundle-sha256 FULL_AUDIT_HASH

# Export copy/files for a native manual action; never calls a platform.
MP_DISABLE_OUTBOUND=1 .venv/bin/python3 -m campaignos.cli export \
  --campaign CAMPAIGN_ID --channel youtube

# Record the truth around a native manual create.
.venv/bin/python3 -m campaignos.cli attempt start \
  --campaign CAMPAIGN_ID --channel youtube --format long-video
.venv/bin/python3 -m campaignos.cli attempt confirm \
  --campaign CAMPAIGN_ID --channel youtube --format long-video --url PUBLIC_URL
.venv/bin/python3 -m campaignos.cli attempt uncertain \
  --campaign CAMPAIGN_ID --channel youtube --format long-video --reason REASON

# Import aggregate metrics and close a retrospective; missing fields stay null.
.venv/bin/python3 -m campaignos.cli metrics import \
  --campaign CAMPAIGN_ID --window 7d --file METRICS_JSON
.venv/bin/python3 -m campaignos.cli close --campaign CAMPAIGN_ID
```

A separate, explicit environment switch is required for a billable TTS adapter. `MP_DISABLE_OUTBOUND=1` must block it. The CLI has no `publish`, `reply`, `follow`, `like`, `vote`, `dm`, or `upload` network command during this pilot.

## 14. Proposed project structure

```text
campaignos/              # standalone repo at ~/Projects/campaignos; package root below
  cli.py                 # local operator commands; no implicit live mode
  contracts.py           # typed versioned campaign/claim/asset/attempt records
  store.py               # SQLite migrations and optimistic transitions
  runner.py              # deterministic single-campaign coordinator
  candidates.py          # exact story revision selection and eligibility
  prompts.py             # versioned, delimited, tool-less Claude prompts
  evidence.py            # 3–7 claim lock and coverage checks
  drafting.py            # structured script/scenes/channel packages
  validation.py          # evidence, originality, policy, rights, media checks
  bundle.py              # immutable manifest and SHA-256 root
  review.py              # one-person review checklist and approval
  attempts.py            # manual slot truth and UNCERTAIN reconciliation
  metrics.py             # aggregate imports, null reasons, outcome cards
  learning.py            # proposals only; no mutation/promotion
  locks.py               # own atomic lock + read-only conservative mindpattern busy check
  slack_approval.py      # Mac-local post-and-poll owner approval with durable lifecycle
  outbound.py            # MP_DISABLE_OUTBOUND-checked boundary for every external call
  redaction.py           # vendored redaction/path-safety helpers (from media_contracts)
  providers/
    base.py              # narrow TTS/render interfaces
    fake.py              # deterministic offline tests
    macos_tts.py         # rehearsal only
    elevenlabs.py        # absent/disabled until separately approved
  render/
    cards.py             # Pillow evidence cards and thumbnails
    ffmpeg.py            # local composition/probe boundary
tests/
  test_campaign_contracts.py
  test_campaign_store.py
  test_campaign_evidence.py
  test_campaign_validation.py
  test_campaign_bundle.py
  test_campaign_attempts.py
  test_campaign_metrics.py
  test_campaign_cli.py
  test_campaign_render.py
  test_campaign_security.py
docs/runbooks/
  pilot.md
data/pilot.db            # git-excluded pilot state
artifacts/<campaign_id>/ # immutable campaign artifacts
```

Mindpattern-v3 and companion-site touch points, each separately approved; no mindpattern production script or scheduler changes:

```text
../mindpattern-rabbit-hole/src/lib/analytics.ts        # safe same-session campaign/channel capture
memory/events_db.py                                    # versioned campaign/channel columns
dashboard/routes/site_analytics.py                     # private aggregate only
dashboard/routes/api.py                                # exact selected story revision hash
```

The implementation plan must ask before adding FFmpeg, changing a database schema, exposing an API, changing the public site's contracts, or enabling any live provider.

## 15. Code and interface conventions

- Python 3.14, existing dependency set unless separately approved.
- Frozen dataclasses or equivalent typed records at module boundaries; explicit `schema_version`.
- Parameterized SQLite, numbered migrations, WAL, short transactions, and connection cleanup.
- Full SHA-256 for identity; shortened hashes only for display.
- UTC timestamps plus explicit campaign reporting timezone.
- Allowed states and reason codes are enums, not free-form dashboard strings.
- Paths derive from validated IDs and must remain under the campaign root.
- Provider/model results are untrusted until schema, length, path, URL, claim, and redaction checks pass.
- Logs include IDs/hashes/statuses, never scripts with secrets, credentials, raw platform-user content, or email addresses.
- Every new outbound-capable boundary checks `MP_DISABLE_OUTBOUND=1` before resolving credentials or making a request.

Example state transition shape:

```python
def transition_campaign(
    conn: sqlite3.Connection,
    *,
    campaign_id: str,
    expected_version: int,
    from_state: CampaignState,
    to_state: CampaignState,
    reason: str,
) -> CampaignRecord:
    """Commit one allowed owner/runtime transition or fail without mutation."""
```

## 16. Testing and safe validation

### Required automated tests

- typed contract round-trips, unknown-field/version behavior, and malformed model output;
- raw-byte story snapshot/hash, duplicate-slug rejection, remote revision mismatch, candidate rejection, three-claim minimum, seven-claim maximum, and two-attempt/45-minute evidence exit;
- 100% consequential-segment claim coverage and exact-quote/source fixtures;
- manual source-import/path/size/redaction/injection fixtures plus a static assertion that pilot evidence code has no network fetcher;
- prompt injection fixtures in story, source, community, and platform text; model roles have zero tools/state handles and only the explicitly permitted subscription auth context;
- injected paid-API/cloud/social/provider credentials are stripped or block preflight; safe mode, empty tools/MCP/plugins/hooks, scratch cwd, stdin prompt, JSON schema, and subscription-auth status are asserted against the supported CLI version;
- CampaignOS's own lock races (concurrent seed/build/resume), stale-lock recovery, the read-only conservative busy check against fixture mindpattern lock states (directory lock held, flock held, harness lock held, all free, stale), and the 06:45–13:00 window guard;
- one-writer campaign state, crash/resume at every state/artifact commit, stale expected-version rejection, and no duplicate campaign from the same story revision;
- deterministic core/leaf/audit hashes, dependency-scoped invalidation, every native edit invalidation, wrong-hash approval rejection, and owner-only approval;
- approval request `SENDING/UNCERTAIN` crash injection, nonce reconciliation, duplicate Slack request/reply idempotency, stale reply rejection, and unavailable owner fail-closed behavior;
- publication slot uniqueness, attempt-start destination-revision recheck/five-minute expiry, crash/ambiguous manual outcome -> `UNCERTAIN`, blocked duplicate, and explicit reconciliation;
- fake TTS/render success, failure, timeout, invalid bytes, path escape, blank frame, missing captions, wrong duration, clipping/silence, and rights failure;
- billable TTS fingerprint/estimate/cap, ambiguous response -> `UNCERTAIN_PROVIDER`, blocked duplicate spend, and explicit reconciliation;
- similarity bootstrap rubric records, exact-duplicate rejection, and no nonexistent calibrated-threshold gate;
- aggregate metric revisions, null reasons, missing-not-zero, UTM validation, and no PII/identity-vault fields;
- `site_events.db` migration plus safe campaign/channel validation, same-session propagation, opt-out, query stripping, aggregate-only export, and rejection of raw query/email/PII fields;
- cash/call/attempt/wall-time/labor caps and no API fallback on Claude usage-limit/overload;
- static/import assertions proving pilot code contains no platform publisher, uploader, follow/like/vote/DM/reply method;
- CLI dry run with `MP_DISABLE_OUTBOUND=1` emits no Slack/TTS/platform network call; the current injected TTS boundary is specifically covered.

### Safe end-to-end rehearsal

Before any public pilot:

1. Build one synthetic fixture campaign entirely offline with fake Claude/TTS/render outputs.
2. Build one real-story **private** campaign using Claude CLI and rehearsal TTS, after owner approves quota use and FFmpeg installation.
3. Crash/restart during evidence commit, render, bundle creation, approval, and manual-attempt simulation.
4. Complete the single review and measure active minutes.
5. Confirm there is no network publishing method and `MP_DISABLE_OUTBOUND=1` blocks the live TTS adapter.
6. Browser-test tagged landing -> story/source/subscribe events -> private campaign aggregate, including opt-out and cleaned shared/internal URLs.
7. Only then request a separate launch decision for campaign 1 and any paid TTS call.

All tests run offline without keys. Live model, TTS, account, and public actions are never CI requirements.

### Repository verification after implementation

```bash
# In the campaignos repository:
.venv/bin/python3 -m pytest tests/ -x -q
git diff --check
git status --short

# In mindpattern-v3, only when its approved touch points change:
.venv/bin/python3 -m pytest tests/ -x -q
graphify update .
graphify check-update .
```

## 17. Acceptance criteria

### Architecture and authority

1. All language-model calls use local `claude -p` under proven subscription authentication; safe-mode/tool/MCP/hook/plugin/env/cwd isolation strips or blocks paid API and application/provider credentials, with no API/SDK fallback or token-dollar reservation path.
2. One Mac-local Python/SQLite runtime in the standalone `campaignos` repository owns the pilot; Temporal, managed PostgreSQL, R2, cloud render, and a runtime abstraction are absent. CampaignOS holds its own atomic lock, refuses to start or proceed while any mindpattern pipeline/harness lock appears held or during 06:45–13:00, and never modifies mindpattern-v3's production scripts, scheduler, or repository contents.
3. Only one build can run; repeated seed/resume commands converge on one campaign for one immutable raw-byte `story_revision_sha256`, duplicate slugs block, and destination revision mismatch invalidates approval/export.
4. No pilot interface can programmatically publish/upload, reply/comment, like/vote, follow, repost, DM, or act on LinkedIn.
5. Models receive no tools, application/provider credentials, database handles, or authority—only the approved Claude subscription auth context; injection fixtures cannot change policy, paths, state, or output schema.

### Evidence and media

6. Each candidate exits evidence lock as approved with 3–7 supported claims or `REJECTED_EVIDENCE` after two model attempts and no more than 45 active owner minutes; four campaigns consume at most six seeds and six weeks.
7. Every consequential script, visual, title/description, and social segment resolves to approved claim IDs; seeded unsupported claims and altered quotes block approval.
8. Every released long video contains at least three sourced story-specific scenes and episode-specific treatment totaling at least the lesser of 90 seconds or 25% of runtime, measured from the render manifest.
9. Audio, video, captions, transcript, source notes, rights, disclosure, duplicate, and destination checks pass deterministic fixtures and the single owner review.
10. Public narration uses only an owner-approved licensed stock voice or Tayler's verified/consented voice; rehearsal voice cannot be accidentally promoted, and an ambiguous paid TTS attempt blocks duplicate spend until reconciled.

### Approval and recovery

11. One Slack owner-only action approves the exact core and current leaf hashes; a core change invalidates all dependent leaves, while **every** leaf edit invalidates that leaf before submission. The durable approval-request lifecycle reconciles ambiguous Slack sends/replies; missing Slack/owner identity fails closed, and local rehearsal review cannot authorize public release.
12. A crash at every SQLite/artifact boundary resumes truthfully without losing an approved artifact or silently repeating model/provider work.
13. One unresolved attempt owns each campaign/channel/format slot; `attempt start` rechecks the destination revision and approved leaf immediately before a five-minute manual-submit window; ambiguous outcomes become `UNCERTAIN` and block another create until explicit reconciliation.
14. `MP_DISABLE_OUTBOUND=1` blocks every campaign provider/external call before credential lookup/network use, including the existing injected TTS boundary after it is hardened; dry-run TTS remains local and non-billable.

### One-person feasibility

15. Campaign 1 requires no more than six active owner hours, campaign 2 no more than five, and campaigns 3–4 no more than four each; the recurring target is 3 hours 35 minutes including community time. One-time implementation remains within its separately approved engineering/owner ceilings or pauses for rescope.
16. Final human review is one full watch plus one 60–90 second audio-only sample and artifact skim, capped at 45 minutes and targeted at 30 minutes after campaign 1; no second rater, kappa, or backup role is required.
17. When Tayler is unavailable, the campaign remains paused with no deadline breach fiction and no model fallback.

### Measurement and economics

18. Every campaign records active minutes, elapsed waits, model/provider/render attempts, incremental cash, existing allocated services, unknown costs, and one-time implementation time both separately and amortized; the dashboard never presents a media-only subtotal as total cost.
19. Campaign/platform/window metrics preserve `null` plus reason for unavailable or immature data; no missing value becomes zero.
20. Campaign reports show discovery, new-viewer/non-follower reach where available, consumption, high-intent response, owned action, guardrails, labor, and cost; follower count is not the north star. First-party attribution is limited to validated campaign/channel fields in the same tagged browser session, CampaignOS receives aggregates only, and `subscribe_success` is not mislabeled as a new contact.
21. No pilot result is labeled causal, statistically significant, winner, champion, or self-improving; every strategy/model/prompt change remains an owner decision.

### Pilot outcome

22. At least three of four campaign attempts reach public manual publication, unless a safety/evidence gate correctly stops them; all attempts retain complete evidence and outcome histories.
23. Across the pilot there are zero unsupported consequential claims, unapproved rights/voice use, uncontrolled duplicate creates, undisclosed AI narration, unplanned spend, or confirmed policy-violating automated engagement actions.
24. After campaign 4, the owner records exactly one top-level `SCALE`, `PIVOT`, or `STOP` decision and one specific classification from the scorecard below; no managed infrastructure work starts without `SCALE` and a new approved spec/ADR.

## 18. Program pause, pivot, stop, and scale rules

### Immediate pause

Pause new exports on any:

- unsupported consequential public claim or materially misleading edit;
- unknown/unapproved media or voice rights;
- secret, PII, private-message, or unsafe source disclosure;
- duplicate/ambiguous post attempt;
- platform warning/removal plausibly caused by the campaign;
- provider charge above the approved cap;
- campaign work interfering with the daily research/newsletter run.

### Stop without finishing four

Stop the pilot if:

- two campaigns fail the owner usefulness score below 4/5 after one revision each;
- a critical factual/rights/privacy incident recurs after the first corrective action;
- cumulative incremental cash reaches the approved cap without explicit owner increase;
- campaign 2 exceeds five active owner hours, campaign 3 or 4 exceeds four, and no simpler format is accepted;
- four campaign attempts cannot be produced from six seeds or within six weeks;
- Tayler does not want to perform the manual community/publishing work the product requires.

### Campaign-4 decision scorecard

Record one of these five specific classifications and its corresponding top-level decision:

| Classification | Required evidence | Top-level decision |
|---|---|---|
| `SCALE_OPERABLE_SIGNAL` | At least three campaigns published; zero critical safety violations; campaigns 3 and 4 each <=4 active hours; at least 20 verified external content starts; at least one platform reports >=10 new-viewer/non-follower exposures; at least three high-intent signals across at least two campaigns; **and** the section-11 first-party attribution extension is implemented and validated (platform-native metrics alone cannot satisfy this row) | `SCALE`—its first committed deliverable is the auto-publish specification (YouTube upload, Transistor API, staged social posting), which needs its own approval; never automatic infrastructure |
| `PIVOT_OPERABLE_WEAK_SIGNAL` | Operability/safety pass but only one or two high-intent signals | `PIVOT`—one more lean audience/format test; no managed infrastructure |
| `PIVOT_UNTESTED_DISTRIBUTION` | Fewer than 20 external starts, no usable new-viewer/non-follower measure, more than one campaign lacks usable measurement, or the section-11 first-party attribution extension was not implemented or failed validation | `PIVOT`—improve manual distribution/measurement before judging content |
| `STOP_NO_SIGNAL` | At least 20 external starts and zero high-intent signals | `STOP`—retire or sharply redesign this format/audience proposition |
| `STOP_NOT_OPERABLE` | Evidence, safety, rights, cash, labor, seed, or owner-willingness gate fails | `STOP`—no CampaignOS expansion |

A verified external content start is a non-internal video view/play, audio start, or qualified campaign page session, deduplicated where the available aggregate permits. A high-intent signal is a substantive reply/comment/email referring to the content, source/CTA click, repeat visit, or tagged subscription-form success; “confirmed new subscriber” is used only when provider evidence distinguishes it. A campaign with at least three external starts and at least 50% average consumption may contribute one consumption signal when only aggregate native metrics exist. Likes and raw impressions do not qualify.

New-viewer/non-follower reach and high-intent actions are separate aggregate tests. CampaignOS does not join them at person level and cannot claim that a particular action came from a non-follower.

These are directional pilot gates, not claims of statistical significance. Low exposure cannot be used to call the content a failure, and high impressions cannot be used to call it useful.

## 19. Risks and tradeoffs

| Risk/tradeoff | Deliberate response |
|---|---|
| Manual publishing limits automation | It tests content and protects accounts before building adapters; manual time is measured. |
| One operator is a single point of pause | Truthful pause is safer than fictional staffing; scale requires actual staffing or narrower SLAs. |
| Four campaigns have weak statistical power | Use descriptive product/labor gates, not A/B winners or automated learning. |
| Claim cap can omit nuance | Claims are selected for one bounded thesis; transcript/source page preserves wider context. |
| Templates may feel repetitive | Require three evidence scenes and an originality rubric, then build fixtures before numeric thresholds. |
| Local Mac can be slow/unavailable | Run after the daily window, measure render time, and defer cloud compute until actual pain exists. |
| Manual metric import is tedious | Four cases do not justify a measurement vault; import time is part of the pilot economics. |
| AI narration may reduce trust | Disclose it, use a licensed/consented voice, compare audience response, and stop if quality is not credible. |
| Cold-start accounts may get little exposure | Pair publishing with useful founder participation and distinguish low exposure from product rejection. |
| Opportunity assistance can become spam tooling | Cap the queue, require manual inputs/current rules, prohibit network action methods, and track negative feedback. |

## 20. Owner decisions required for approval

The recommendation is shown first. The owner may change it, but all nine decisions need an explicit answer or acceptance of the default.

1. **Audience wedge:** approve “builders/operators deciding whether and how to trust AI agents and AI infrastructure” for all four campaigns.
2. **Human time:** approve campaign 1 up to six active hours, campaign 2 up to five, campaigns 3–4 up to four each, with a recurring target of 3 hours 35 minutes including three 15-minute community sessions.
3. **Cash cap:** approve $85 before tax in cumulative new pilot vendor spend across the six-week pilot horizon (covering up to two ElevenLabs billing cycles and, if Decision 5 later approves it, up to two Transistor cycles), no auto-recharge, while showing existing Claude/Resend allocation separately.
4. **Voice:** approve an ElevenLabs licensed stock voice on Creator for public pilots; use macOS `say` only for rehearsal. A Tayler clone requires a separate verified-consent decision.
5. **Podcast:** keep campaigns 1–2 audio local-only (the YouTube video carries the narration); defer Transistor until those campaigns pass audio quality, then allow a separate $19/month decision and manual upload for campaign 3.
6. **Accounts/community:** name the X and Bluesky account identity, up to three Reddit communities already familiar to Tayler, and the initial topical watchlist. Founder-led participation is recommended.
7. **Local dependency:** approve installing FFmpeg on the Mac after the implementation plan identifies the exact package/license and protects the 06:45–13:00 daily window.
8. **Measurement and exit:** approve planning the minimal same-session campaign/channel event extension (aggregates only, no email/identity join) and approve the pause/stop plus campaign-4 `SCALE / PIVOT / STOP` scorecard as written. Schema/API/site changes still require review in Phase 2 before implementation. A `SCALE` outcome's first committed deliverable is the auto-publish specification (YouTube upload, Transistor API, staged social posting); to keep that path unblocked, Tayler may start YouTube Data API app-verification paperwork during the pilot — paperwork only, no upload code.
9. **One-time build budget:** approve a provisional ceiling of 80 engineering execution hours plus 12 active owner-review hours through private rehearsal. The scope now includes standalone-repo scaffolding and vendoring the receipts/approval/redaction helpers, and no longer includes rewriting mindpattern-v3's launch scripts. Phase 2 must supply an estimate; exceeding either estimate/cap requires scope reduction or a new decision before more work.

Account facts still required before public launch—not before offline implementation planning—are a proven Claude subscription-auth context for the sanitized CLI (passing as of the 2026-07-12 recheck; re-verified at launch), current Resend plan/usage, YouTube channel eligibility, voice-provider commercial rights, account policy state, and the exact destination/audio hosting path. The companion-site/backend attribution and story-revision contracts must also pass their separately approved migration, privacy, API, and browser checks before they can support `SCALE_OPERABLE_SIGNAL`.

## 21. Boundaries

### Always

- preserve the Claude CLI subscription boundary;
- keep model/provider/platform text untrusted and models tool-less;
- require source-backed claims, rights, disclosure, deterministic checks, exact core/leaf approval, and truthful attempt state;
- preserve missing metrics as null and separate observation from inference;
- record human minutes and all cost categories;
- keep implementation and tests offline by default;
- stop at the approval gate before planning or coding.

### Ask first

- adding FFmpeg or any Python/system dependency;
- adding/changing SQLite, public API, site, analytics, email, or media schemas;
- any Claude live pilot run beyond ordinary development use;
- any billable TTS, podcast, storage, model, image, or video provider;
- any account/OAuth/API setup, public upload/post/email, or production data access;
- any voice clone, realistic synthetic media, or cross-repository change.

### Never in this pilot

- paid Anthropic API/SDK or silent model/provider fallback;
- managed workflow/database/render infrastructure;
- automatic platform publishing or conversational engagement;
- browser scripting against social platforms;
- unsupported claims, fabricated evidence, hidden AI narration, unverified voice rights, or automatic safety waiver;
- self-modifying prompts/code/config, auto-promotion, or causal claims from four campaigns;
- continue merely because infrastructure has already been built.

## 22. Evidence appendix

### Repository evidence

- Model/subscription: `docs/spec-research-reliability.md:41-70`; `orchestrator/agents.py:run_single_agent`; `core/claude_cli.py:run_claude_process`; `core/llm.py:run`.
- Current state: `orchestrator/pipeline.py:Phase`, `PHASE_ORDER`, `VALID_TRANSITIONS`.
- Mac schedule: `deploy/com.mindpattern.pipeline.plist`; `run-launchd.sh:84-85`.
- Story gate/evidence: `orchestrator/site_content.py:is_publishable_site_story`; `orchestrator/site_content_engine.py:_claim_evidence_candidates`.
- Audio: `orchestrator/audio_briefing.py:build_audio_script`, `build_tts_audio`, `audio_artifact_paths`; `dashboard/routes/api.py` audio endpoints; companion site `src/components/briefing/audio-briefing-player.tsx`.
- Video: `orchestrator/video_scripts.py:VideoScriptPackage`, `build_video_script_package`; `tests/test_video_scripts.py`; `tests/test_media_feature_safety.py`.
- Media safety: `orchestrator/media_contracts.py:EvidenceReference`, `PublicArtifactMetadata`, `redact_sensitive_text`, path validation.
- Resend: `orchestrator/newsletter.py:send_newsletter`, `broadcast_to_subscribers`; `orchestrator/runner.py:_phase_deliver`; `tests/test_newsletter.py`; `tests/test_newsletter_receipts.py`.
- Approval/receipts: `social/approval.py:ApprovalGateway`; `core/receipts.py:outbound_allowed`, `claim`, `release`.
- Deployment: `fly.toml`; `start.sh`.
- CI: `.github/workflows/test.yml`; Python 3.14 and offline pytest expectations in `AGENTS.md`.

### Safe validation already recorded by v1

V1 recorded this focused offline result before it was rejected:

```text
.venv/bin/python3 -m pytest -q tests/test_audio_briefing.py tests/test_video_scripts.py tests/test_media_feature_safety.py tests/test_social.py tests/test_posting.py tests/test_approval.py tests/test_events_api.py tests/test_site_analytics.py tests/test_analyzer.py --tb=short

193 passed, 1 Starlette/httpx deprecation warning in 0.62s
```

This confirms only the tested current mocked behavior. It does not prove live TTS, FFmpeg rendering, public uploads, RSS, platform access, engagement, or growth.

### External operating evidence

- X's current recommendation and automation documents support out-of-network discovery while prohibiting non-API scripting, duplicate/spam behavior, and unsolicited automated replies.
- Reddit's official organic guidance recommends listening, commenting before posting, communicating as a person, and posting sparingly; subreddit rules remain local and current.
- Bluesky's official developer/community guidance prohibits bulk/artificial engagement; custom feeds and search create topic-based discovery.
- YouTube's official documentation emphasizes relevance, appeal, engagement/satisfaction, accurate packaging, and account/OAuth constraints rather than requiring an existing follower base.

These sources support the opportunity; they do not predict campaign results.

## 23. Reconciliation of the rejected v1 review

| Adversarial finding | Resolution in v2 |
|---|---|
| Paid API/token architecture contradicted owner constraint | Claude CLI subscription is a hard boundary; calls/attempts/wall time replace token-dollar reservations; cloud model workers are excluded. |
| Human workload and two-rater math did not close | One human role, one combined review/action over exact hashes, no kappa, no independent human grader, no named backups, realistic active-minute budget. |
| Similarity gate deadlocked campaign 1 | Exact duplicate checks plus recorded owner rubric bootstrap campaigns 1–4; calibrated semantic thresholds are deferred. |
| 70% bespoke visuals were infeasible | Three evidence scenes and the lesser of 90 seconds or 25% story-specific runtime; template time is allowed and labor is measured. |
| Evidence lock could stall forever | Cap at 3–7 claims, two model attempts, 45 owner minutes, then reject the story and choose another; cap the pilot at six seeds/six weeks. |
| $42–50 headline omitted dominant costs | Every cost category is visible; pilot and optional costs are staged; Temporal's $100 minimum and an illustrative $176 managed subtotal are explicit. |
| L2–L4/vault had no statistical power | No vault, experiment winner, holdout, canary, or automatic learning in four campaigns; proposals only. |
| Dual runtimes doubled the product | One local runner only; a future ADR must choose one managed runtime. |
| Mac rendering was banned without pilot evidence | Mac-local render after the daily window; cloud compute requires measured pain. |
| Spec was too large to approve | The controlling scope is campaigns 1–4 with nine owner decisions and 24 acceptance criteria; scale-only ideas live in a separately non-authoritative appendix. |
| Confirmed phase list omitted `INIT` | Correct sequence is recorded from `orchestrator/pipeline.py`. |
| Five-second security claim lacked detector | Deleted; the spec distinguishes local pause/kill propagation from incident detection. |
| Exploratory results could steer informally | Editorial changes are allowed but explicitly labeled judgment, not causal promotion. |
| No sunk-cost/program kill rule | Immediate pause, early-stop, exposure, labor, high-intent signal, and `SCALE / PIVOT / STOP` rules are explicit. |

A separate fresh-context, repository-grounded review of v2 initially returned `REVISE`. It found local-runtime lock races, absent story-revision identity, the current TTS kill-switch gap, unsafe Claude environment/config inheritance, inconsistent call/labor arithmetic, an impossible email bridge, non-durable Slack approval, incorrect site-audio reuse, SSRF exposure, native-edit approval gaps, and measurement overclaims. The current revision resolves each item. A final narrow re-audit marked every item `PASS`.

A 2026-07-12 second adversarial review re-verified the repository claims (nearly all held; the spec was correct where the project `CLAUDE.md` phase list was stale) and found: (a) the $50/one-month cash cap contradicted the six-week horizon and Decision 5 — restated as an $85 pilot-total cap; (b) `SCALE_OPERABLE_SIGNAL` was reachable from platform-native metrics alone while section 11 forbade it — the attribution precondition is now in the scorecard row; (c) the seed-dedup rule only covered cross-date slug collisions while same-date bare-slug/date-prefixed duplicate files with differing content actually exist — the rule now rejects any ambiguous resolution; (d) the logged-out Claude auth blocker was stale (now `loggedIn: true`, Max); (e) `_clean()` lives server-side in `memory/events_db.py`, not `analytics.ts`; (f) the five-minute submit window could not fit a YouTube upload — it now covers only the final publish action; (g) no caption-timing source existed in the dependency set — Phase 2 must specify one. It also confirmed the lock-fragmentation claim is understated: `slack_bot/bot.py:_acquire_mutex` is defined but never called, so the current bot has no collision protection at all, strengthening the lease-unification requirement. All items are reconciled in this revision.

Later on 2026-07-12 the owner directed that CampaignOS be a standalone project. This revision moved the runtime, state, artifacts, commands, and tests to a new `campaignos` repository consuming mindpattern-v3 through three explicit contracts (read-only story input plus a revision-hash endpoint, a read-only busy-check lock convention, and aggregate-only attribution imports). The shared-lease rewrite of mindpattern's production scripts was dropped; unifying mindpattern's fragmented locks is now that repo's own backlog item.

## 24. Approval gate

This document remains **unapproved** until:

1. the fresh-context v2 adversarial review is reconciled;
2. Tayler explicitly answers or accepts Decisions 1–9; and
3. Tayler writes an unambiguous approval tied to this file/date, such as:

> I approve `2026-07-11-campaignos-four-campaign-pilot-spec.md` with Decisions 1–9 as recorded. Proceed to Phase 2 planning only.

Approval authorizes a plan and task breakdown, not live providers, account changes, public publishing, dependency installation, production access, or implementation beyond the separately approved Phase 2 scope.

**Approval record:** Tayler approved on 2026-07-12 in a working session ("i approve"), following two adversarial reviews and the standalone-repo conversion. Decisions 1–5 and 7–9 stand as recorded above. Decision 6 (account identities, up to three Reddit communities, initial watchlist) is open and must be answered before campaign 1's public launch; it does not block Phase 2 planning per the account-facts clause in section 20.
