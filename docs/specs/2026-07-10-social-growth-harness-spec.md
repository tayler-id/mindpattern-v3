# MindPattern social growth harness: research, strategy, and build specification

**Status:** DRAFT FOR OWNER REVIEW — no implementation authorized  
**Date:** 2026-07-10  
**Repositories reviewed:** `mindpattern-v3` and `mindpattern-rabbit-hole`  
**Planning horizon:** first 90 days from launch  
**Owner assumption:** Tayler is the visible founder/operator; MindPattern is the product and evidence engine.

## Progress

- [x] Mapped the existing social creation, approval, posting, engagement, memory, and analytics code.
- [x] Reviewed the public site's positioning, acquisition paths, story surfaces, subscription flow, sharing, and first-party analytics.
- [x] Reviewed current X, Reddit, and Bluesky automation and community rules.
- [x] Researched current evidence about consistency, replies, community participation, and newsletter growth loops.
- [x] Defined a repository-specific organic growth strategy for a small starting audience.
- [x] Specified the target harness, typed contracts, states, approval modes, guardrails, metrics, tests, and rollout.
- [ ] Owner confirms account identity, time budget, API budget, target reader, and acceptable automation levels.
- [ ] Implementation plan is approved. This document does not authorize code changes or live posting.

## Executive decision

MindPattern does not primarily have a content-production problem. It already has a large, source-backed archive, daily findings, public stories, briefings, entity pages, a graph, dynamic social cards, and an unusually strong Agentic Evals campaign asset. Its immediate growth problems are:

1. A new visitor is not told quickly enough who the site is for or what it helps them do.
2. The social pipeline appends the generic homepage URL instead of the exact public story that supports the post.
3. Social visits and subscriptions cannot be attributed to a campaign, platform, or content variant.
4. The scheduled production run disables social by default, so the existing pipeline is not an active distribution system.
5. The current system creates posts, but it does not run a measurable audience-development loop.
6. X is half-present in code but disconnected; Reddit publishing does not exist.

The right strategy is a founder-led, evidence-first media loop:

```text
MindPattern evidence -> one useful platform-native insight -> real conversation
        -> exact source-backed story -> contextual subscribe prompt
        -> newsletter/return visit -> reader feedback and sharing
        -> next research question and content experiment
```

This is not a high-volume syndication bot. Automation should remove research, formatting, scheduling, policy checking, attribution, and measurement work. Tayler should remain responsible for judgment-heavy replies, all Reddit publishing, and LinkedIn publishing.

### Recommended automation boundary

| Channel/action | Launch mode | Why |
|---|---|---|
| Bluesky original posts | Human-approved, then eligible for low-risk auto-publish after a shadow period | Existing client and pipeline are mature enough to reuse; conversation quality still needs calibration. |
| Bluesky replies | Surface opportunities locally; Tayler writes/posts through the native UI during the first 90 days | Replies are the relationship-building work, and bulk/automated notifying interactions carry trust and policy risk. |
| X original posts | Human-approved through the official API; limited evergreen auto-publish only after X use-case review and canary success | X permits useful informational automation, but bans duplicate/spam behavior, automated trending-topic posts, and website scripting. |
| X proactive replies | Local opportunity list and owned-evidence notes only; Tayler writes/posts through the native UI | No AI reply generator or reply adapter is in this 90-day harness, even if a future approval becomes possible. That would require a separate spec and owner decision. |
| Reddit discovery | Manual only until Reddit grants written approval for this business-adjacent use | Reddit requires explicit API approval and written approval for commercial/business use. The owner cannot self-declare an exemption. |
| Reddit posts/comments | Community-rule checklist and evidence package; Tayler writes/posts through Reddit's native UI | This is ordinary human participation, not a Devvit automation exemption. Reddit's general terms, spam rules, disclosure duties, and community rules still apply. |
| LinkedIn | Prepare copy and media package only; manual publish | This is the owner's requested boundary and the repo already treats LinkedIn engagement as manual. |

## Objective

Build a reliable harness that turns MindPattern's existing research into platform-native conversations, sends interested readers to the exact supporting page, converts qualified readers into repeat readers/subscribers, and learns which topics, angles, formats, communities, and calls to action actually work.

The harness must optimize for this funnel, in order:

1. Meaningful conversations with the right people.
2. Qualified profile visits and site visits.
3. Engaged reading sessions.
4. Newsletter subscriptions.
5. Returning readers, replies, shares, and referrals.

Follower count is a useful lagging indicator, not the north-star metric.

## Confirmed current state

### Existing pipeline worth preserving

- `social/pipeline.py:SocialPipeline` already orchestrates topic selection, a creative brief, parallel platform writers, blind critics, deterministic policy checks, humanization, an expeditor, Slack approvals, posting, feedback capture, and deferred posts.
- `social/approval.py:ApprovalGateway` has thread-scoped, owner-only Slack approvals that fail closed on ambiguous replies.
- `core/receipts.py` provides an outbound kill switch and idempotency receipts before external actions.
- `memory/social.py` stores posts, embeddings, editorial feedback, engagements, pending posts, duplicate checks, and voice exemplars.
- `social/posting.py` contains retrying clients for Bluesky, LinkedIn, and X plus canonical result shapes.
- `social/engagement.py:EngagementPipeline` can search Bluesky, filter candidates, rank them, draft replies, request approval, post, and record outcomes.
- `policies/social.json` provides deterministic language and cadence checks for Bluesky and LinkedIn.
- Public stories have dynamic 1200x630 Open Graph cards and source-backed claim evidence.
- `memory/events_db.py` and `dashboard/routes/site_analytics.py` already collect privacy-safe page/click/referrer/subscription events and expose an internal summary.

### Confirmed gaps

1. `run-launchd.sh` defaults `MP_LAUNCHD_SKIP_SOCIAL` to `1`, adding `--skip-social`; normal scheduled runs therefore skip both social and engagement.
2. The ignored local `social-config.json` currently enables LinkedIn and Bluesky only. X and Reddit are not configured.
3. `social/posting.py:XClient` exists, but `SocialPipeline._init_platform_clients()` instantiates only Bluesky and LinkedIn.
4. `social/writers.py:PLATFORMS`, agent definitions, and `policies/social.json` contain no live X or Reddit writing contract.
5. Git commit `827d1a9` deliberately removed X from the active pipeline after stale X draft files contaminated expeditor runs. Re-enabling X without per-run artifact isolation would recreate that class of failure.
6. Reddit code is research-only (`preflight/reddit.py` and `tools/reddit-fetch.py`); no Reddit publishing adapter has existed in discoverable Git history.
7. `social/engagement.py` is Bluesky-only despite broader comments in its module documentation.
8. `social/eic.py` produces source URLs and a fixed homepage link, but no public story slug, canonical landing URL, campaign ID, or conversion goal.
9. `social/writers.py:_build_writer_agent_prompt()` explicitly tells every writer to end with `https://mindpattern.ai`.
10. The first-party event schema records only event, target, path, referrer domain, anonymous ID, and value. It cannot identify platform, campaign, post, or variant.
11. The site's `ShareButton` emits `share`, but `memory/events_db.py:ALLOWED_EVENTS` does not accept it, so the first-party database silently drops that signal.
12. Story pages offer X, LinkedIn, native share, and copy-link controls, but no Bluesky or Reddit share controls.
13. The subscribe form exists only near the bottom of the very long homepage; public story pages have no contextual end-of-story form.
14. `/blog/{date}` and `/briefings/{date}` expose the same underlying report with competing canonicals, splitting links and analytics.
15. The homepage shows the archive before it explains the outcome for a reader. Its current headline, "AI Research Intelligence," is too broad for cold traffic.
16. Outbound safety is fragmented: the main post path uses receipts, while Slack posting and engagement replies/follows can bypass the same receipt/kill-switch boundary.
17. Human-edited Slack copy is not passed through the full deterministic validation sequence again before posting.
18. The engagement path can auto-follow after an approved reply; following is unnecessary for this harness and creates avoidable platform risk.
19. Successful API results are not consistently copied into `social_posts.platform_post_id`, preventing reliable metric reconciliation.
20. Shared EIC, brief, draft, and verdict filenames are unsafe for overlapping runs; the stale-X incident is one instance of a wider artifact-isolation defect.
21. Writer functions already contain writer/critic revision loops, after which `SocialPipeline` performs another critic/rewrite cycle. This adds latency and model cost without a clearly measured benefit.
22. A live homepage check on 2026-07-10 showed a 2026-07-08 edition and contradictory corpus counters: the header reported 15,627 indexed findings while the trending block reported zero findings and zero sources. Driving new readers into visible freshness/data contradictions would erode trust.
23. The homepage subscription form appears after a very large wire/archive listing rather than near the initial value promise. Even a qualified visitor must travel too far before the primary conversion opportunity.
24. `social/posting.py:_api_call_with_retry()` retries connection errors/timeouts for all HTTP methods, including X/Bluesky create calls. If a platform accepts a POST but the response is lost, the client can duplicate it before an outer outbox ever sees `unknown_outcome`.
25. Current approvals are mostly in-process decisions rather than durable records bound to approver + exact content hash + validation hash; mutation-safe revalidation cannot be enforced from the existing return shape alone.
26. `site_events.db` intentionally lives only in production while growth lifecycle data would live in local `memory.db`; the existing analytics summary has no per-publication aggregate/cursor boundary to join them safely.
27. The site share component reuses `window.location.href`, so a visitor can re-share the campaign query that acquired them—or even propagate `mp_optout=1`—and corrupt downstream attribution/analytics behavior.
28. The site repository has build/lint scripts but no automated browser-test runner for the required tagged-story -> subscription, redirect/canonical, responsive CTA, or share-URL checks.

### Audit verification run

Safe, local tests were run without credentials, model calls, or platform writes:

```text
.venv/bin/python3 -m pytest -q tests/test_social.py tests/test_posting.py tests/test_events_api.py tests/test_site_analytics.py
72 passed, 1 Starlette/httpx deprecation warning in 0.42s

.venv/bin/python3 -m pytest -q tests/test_policies.py
36 passed in 0.09s
```

These results confirm that the currently covered behavior is green; they do not prove end-to-end X or Reddit readiness. In particular, mocked tests exercise the isolated X client and generic writer calls without requiring the missing X prompt, policy, pipeline initialization, or live orchestration. One policy test also treats X as passing when no length error appears even though X is absent from the active policy configuration. The proposed tests explicitly close those false-confidence gaps.

### Product direction inferred from repository evidence

The site is moving from a daily AI-news archive toward a living public-intelligence graph: source-backed stories, entities, narrative arcs, provenance, and connections. The best initial audience is narrower than “anyone interested in AI”:

> Builders, technical founders, researchers, and operators who need to understand what changed in AI systems, what the evidence actually says, and what to do about it—without spending hours in feeds.

This positioning is an inference for owner review, based on `mindpattern-rabbit-hole/PRODUCT.md`, the feature-discovery runbook, the current corpus, and the site's strongest story pages.

## What the external evidence says

### Cross-platform lessons

- Buffer's 2025 analysis of more than 100,000 users found that consistent posters received substantially more per-post engagement than inconsistent posters. This is observational, not proof that frequency alone causes growth; the actionable lesson is to maintain a sustainable cadence long enough to learn, not to maximize volume.
- Buffer's 2025 reply analysis covered nearly two million posts from more than 220,000 accounts. Posts where the owner replied to comments outperformed that account's baseline on all six measured networks, including roughly 8% on X and 5% on Bluesky. The authors explicitly warn that reverse causality remains possible. The safe conclusion is that conversation deserves operating time and measurement.
- X's own recommendation documentation says conversation replies are ranked using predicted likes, replies, reposts, negative feedback, author/viewer relationships, and whether the root author replied. A useful reply can create discovery, but low-quality reply automation creates policy and reputation risk.
- Metricool's vendor-connected 2026 dataset reports weakening outbound link clicks on X. Its sample is not representative of every account, but it reinforces the safer strategy: make each post useful natively and treat the click as the next step, not the only value.
- Pew's panel of established news influencers shows X and Bluesky currently function as complements rather than substitutes. Its large-account sample does not predict MindPattern's cold start, but it supports maintaining both while measuring their different roles.
- Reddit's own business guidance says publishers should act like trusted community participants who happen to publish, not organizations using Reddit for distribution. Its suggestion to diversify across 10–15 communities is vendor guidance, not a cold-account target; MindPattern should observe broadly but actively participate in only 3–5 at first.
- Bluesky's starter packs and custom feeds are explicit community-discovery mechanisms. A useful “AI agent builders and eval practitioners” starter pack can earn distribution by helping the community, not by advertising MindPattern.
- Newsletter referrals and creator recommendations are widely used by larger publications, and vendors report positive case studies, but that does not prove they will work for MindPattern. Do not build rewards before a small base of engaged readers exists; begin only with a simple post-subscribe share prompt and measure it.

### Policy facts that constrain the design

#### X

- Automation must use the official API; scripting the website may cause permanent suspension.
- Helpful informational posts may be automated.
- Duplicate or substantially similar automated posts are prohibited.
- Automated posts about trending topics are prohibited.
- Keyword-triggered unsolicited auto-replies are prohibited.
- AI-powered reply bots require prior written, explicit X approval.
- Automated likes are prohibited, and aggressive/indiscriminate following is prohibited.
- Before any changed use case or automatic original-post canary, confirm that the registered X developer use case, account labeling/disclosure, responsible human operator, and linked human account satisfy current X requirements.
- Current pay-per-use pricing makes reads and link posts a real operating-cost concern: X lists post reads at $0.005 per resource, ordinary creates at $0.015, and creates containing a URL at $0.200. Prices are changeable, so the harness must read a configured budget rather than hard-code economics.

#### Reddit

- Reddit's June 2026 Responsible Builder Policy requires explicit approval before Data API access and explicit written approval for commercial uses.
- Apps must be registered, transparent, narrowly scoped, and labeled.
- Identical or substantially similar automated content across subreddits is prohibited.
- Reddit's spam policy prohibits repeated unsolicited mass engagement, automated or manual.
- Devvit apps that post/comment for a user require a separate explicit manual action. This does not by itself authorize an off-platform growth harness; the broader API, commercial-use, spam, attribution, retention, and deletion obligations still control.
- Each subreddit has its own rules and norms. A global “10% self-promotion” rule is not a platform guarantee and must not be treated as permission.

#### Bluesky

- Bluesky exposes first-class posting APIs and custom-feed infrastructure.
- Its community rules prohibit spam and artificial manipulation of reach, followers, or engagement.
- Commercial/product-related content must be transparently disclosed where the relationship is not already obvious; disclosure is a validator field, not a Reddit-only concern.
- Technical rate limits are ceilings, not recommended content cadence.

#### Platform content sent to models

The current agent pipeline uses an external model provider. Before any X, Reddit, or Bluesky post/comment text is included in a model prompt, complete and record a data-handling review covering the platform's developer terms, the model provider's retention/training settings, deletion propagation, permitted redistribution, and the registered use case. Until that review passes, rank opportunities with local metadata/embeddings and let Tayler read and write replies in the native UI. Prompt-injection filtering is necessary but does not satisfy licensing or data-processing terms.

## Growth strategy

### Positioning to test

**Short promise:** “Source-backed intelligence for people building and operating AI systems.”

**Expanded promise:** “MindPattern tracks what changed across AI tools, models, agents, and infrastructure, connects the evidence, and explains what builders should do next.”

**Founder line:** “I built MindPattern because I could not keep up with the AI ecosystem and still verify what mattered.”

The brand should consistently distinguish:

- **MindPattern:** the public intelligence system and archive.
- **Tayler:** the accountable human voice, editor, and conversation participant.
- **The Ramsay Research Report:** the email/briefing product. If this name remains, the site needs a one-line relationship between it and MindPattern.

### Content pillars

Every post must belong to one of six repeatable, repository-native pillars:

1. **What changed:** one important development from today's findings, with why it matters now.
2. **Claim / evidence / take:** a precise claim, the source that supports it, and Tayler's interpretation.
3. **Agent failure autopsy:** a concrete reliability, evaluation, orchestration, or tool-use failure and the operator lesson.
4. **Rabbit-hole connection:** two sources or events that become more useful when connected.
5. **Operator playbook:** a short checklist or decision rule derived from the evidence.
6. **Week in agent systems:** a recurring synthesis of the week's strongest signals, disagreements, and open questions.

Avoid generic AI news summaries, product changelogs without a reader outcome, inflated predictions, and “MindPattern found this” product-demo framing.

### One source asset, different native expressions

Cross-platform reuse must share evidence, not copy. For one published story:

| Surface | Native expression |
|---|---|
| X | A concise claim/take, a small evidence thread, or a manually approved reply/quote post. Most posts are useful without clicking. |
| Bluesky | A compact technical observation, source card, or reply in a relevant feed/community. |
| Reddit | A text-first explanation, question, teardown, or useful comment written for one subreddit. Link only when the community permits and the link materially completes the answer. |
| LinkedIn | A manual founder/operator narrative with the decision, mistake, or lesson; not a pasted X thread. |
| Site | The exact story, briefing, entity, research report, or narrative arc that substantiates the social claim. |
| Email | The broader synthesis and a reason to return; it should ask for a reply periodically to create a research feedback loop. |

### Channel playbooks

All weekly numbers below are human operating ceilings for a Monday–Sunday `America/New_York` week, not scheduler-enforced promises. The scheduler enforces separate programmatic-original caps and shows outstanding/unreconciled manual packages before scheduling; it cannot know about unrecorded native-UI actions and must not “make up” missed manual activity automatically.

#### X: discovery through useful participation

Initial weekly ceilings, not quotas:

- Up to 4 original posts, of which no more than 2 contain a site link.
- Up to 8 high-specificity, natively written replies to relevant builders/researchers.
- At most one recurring evidence thread or operator checklist.
- Reply to substantive responses on MindPattern posts when Tayler can add something useful, normally within one working day.

The harness should maintain a small curated account/list set and current MindPattern entities, then use local scoring to surface opportunities where the archive contributes a fact, source, counterexample, or implementation lesson. It must never auto-like, auto-follow, auto-DM, post from a scraped browser, or send unsolicited automatic replies. Opportunity performance is judged by sampled reply quality and qualified reader outcomes—not by satisfying a reply count or attracting a like from the target.

#### Bluesky: become part of a technical neighborhood

Initial weekly ceilings, not quotas:

- Up to 4 original posts and up to 8 thoughtful, natively written replies.
- Participate in a small set of relevant custom feeds.
- Build and maintain an “AI agent builders and eval practitioners” starter pack that genuinely features other people.
- Test one recurring format—such as “What changed in agent systems today”—for six weeks before judging it.

The existing API client and search pipeline make Bluesky the safest first automation target.

#### Reddit: earn permission before asking for traffic

Initial weekly ceilings after a two-week observation/contribution period:

- Up to 3 helpful comments per week across a curated registry of communities.
- At most one original, text-first post per week, only where rules and account history allow.
- No duplicate cross-posting and no automatic publishing.
- Disclose the MindPattern relationship whenever it is relevant.
- Track removals and moderator feedback as product learning, not as a prompt to evade filters.

Candidate community categories—not a pre-approved posting list—include agent frameworks, language-model engineering, machine learning, local models, AI safety/evaluation, developer tools, and technical founder communities. Every actual subreddit requires a dated rule snapshot and human approval before use.

Use Reddit first to learn exact questions and language. Traffic is a secondary outcome. If an answer is valuable without a link, publish it without a link.

#### LinkedIn: keep the human advantage

Prepare at most two high-signal drafts per week for manual posting:

- one founder/operator lesson;
- one evidence-backed industry conclusion or carousel.

The harness may prepare copy, source notes, alt text, media, and a suggested first comment. It must not publish or engage automatically.

### Five cold-start moves

1. **Fix the profile-to-story path.** Each bio and pinned post should say exactly who MindPattern helps and point to a curated “start here” story or research page—not an undifferentiated homepage.
2. **Launch the Agentic Evals campaign.** Reuse the existing ten-panel carousel as a two-week multi-platform series, with one specific claim per post and the full research page as the destination.
3. **Build a relationship map.** Curate 30–40 people/accounts and observe 10–15 possible Reddit communities around agent evaluation, runtime reliability, orchestration, developer tools, and AI research. Actively participate in only 3–5 communities at first. The goal is to learn and contribute, not harvest followers.
4. **Run a daily conversation block.** Spend 25–35 minutes writing a small number of excellent replies. Local automation can organize evidence and opportunities; Tayler supplies and posts the judgment.
5. **Create one owned growth loop.** Add a contextual story subscription prompt, a useful welcome sequence, and a post-subscribe sharing prompt before chasing more impressions.

### Collaboration strategy

Starting from a small audience, borrowed trust is more valuable than generic reach. Each month:

- invite two practitioners whose work appears in MindPattern to correct, expand, or disagree with a finding;
- publish one short, source-backed Q&A or joint teardown;
- make the collaborator the subject, not MindPattern;
- provide a clean share package, but never require promotion;
- record referred visits, engaged sessions, and subscriptions separately from ordinary social traffic.

No automated cold DMs are in scope.

## Acquisition and conversion prerequisites

These are growth-system prerequisites, not optional website polish:

1. Resolve every selected finding/topic to a versioned `ContentAsset` (story, briefing, entity, arc, research page, or explicit no-link asset) with a canonical URL and claim evidence. Do not assume every destination has a story slug.
2. Define one join key: `publication_id` is the stable internal identifier carried by the final draft, approval, publish job/outcome, tracked URL, platform metric snapshot, and site event. `platform_post_id` is a separate external identifier and must never be overloaded as the site join key.
3. Build tracked URLs with allowlisted query fields: `mp_campaign`, `mp_publication`, `mp_variant`, and `mp_platform`. Values are opaque ASCII IDs matching `^[a-z][a-z0-9_]{7,63}$`; platform is an enum. Sanitize and cap the closed event schema before sending to either the first-party endpoint or Vercel Analytics.
4. Use a versioned last-touch rule: retain the last valid social attribution in first-party browser storage for at most seven days, respect the existing analytics opt-out, and attach it only to privacy-safe events. Record a conversion only when the subscription endpoint confirms a newly created contact; an existing-contact response is not a new subscription. Keep email in Resend only—the event database receives opaque campaign fields, never email or provider contact IDs.
5. Add a private, bearer-protected campaign-aggregate endpoint on the Fly service. It computes absolute, versioned per-publication/window aggregates **and cross-publication weekly/channel aggregates** inside `site_events.db`. Only the production service uses anonymous IDs to deduplicate the weekly north-star; it exports the resulting unique count, never the IDs. Each row includes `aggregate_revision`, `as_of`, fixed window bounds, definition version, and cohort maturity. A daily job recomputes a rolling 35-day lookback and emits revisions when late events arrive or cohorts mature even without a new event; the cursor enumerates new/changed revisions. Local import upserts only a higher revision and never receives raw anonymous event rows.
6. Construct share URLs from the page's canonical origin/path, stripping all query strings, fragments, and `mp_optout`. Do not let one visitor re-share the campaign that acquired them. A future reader-referral ID must be a separate, explicitly designed attribution source.
7. Add an end-of-story subscribe form or CTA whose copy matches the story/topic and preserves the valid seven-day attribution through the confirmed new-contact event.
8. Accept and report the `share` event; add Bluesky and Reddit share options.
9. Consolidate `/blog/{date}` into `/briefings/{date}` with redirects and one canonical route.
10. Add an above-the-fold value statement and a visible “start here” path to the homepage.
11. Add an About/methodology/editorial page that explains Tayler's role, automation, verification, corrections, and provenance.
12. Define readiness by asset type and reason code. A linkable asset must be published, pass provenance/redaction requirements, contain the sources/evidence required for its claim type, return HTTP 200 with the expected canonical, and have no active site-health/freshness incident. Store its artifact hash plus `checked_at`/`expires_at`; revalidate within 30 minutes of publish and after any approved-copy edit. Failure is a hard stop, not a warning.

## Harness architecture

```text
Daily findings + public stories + briefings + analytics + platform signals
                               |
                  0. Exclusive mode/cutover guard
                               |
                        1. Asset resolver
                               |
                         ContentAsset
                               |
                +--------------+--------------+
                |                             |
        2. Content candidates          3. Conversation opportunities
                |                             |
                +--------------+--------------+
                               |
                    4. Relevance/risk scorer
                               |
                    5. Platform-native writers
                               |
         6. Evidence + policy + voice + duplicate validators
                               |
                       7. Approval router
                 +-------------+-------------+
                 |             |             |
          auto-eligible   human approval     manual package
       evergreen original  API originals  all replies/Reddit/LinkedIn
                 |             |                 |
                 +-------------+                 |
                               |                 |
                  8. Scheduled transactional     |
                     outbox + official APIs      |
                               |                 |
             9. Receipts, outcomes, and          |
                uncertain recovery               |
                               |                 |
                               +--------10. Manual action record
                               |
          11. Platform metrics + private site aggregates
                               |
                   12. Experiment evaluator
                               |
                   13. Weekly learning proposal
                               |
                   Human accepts/rejects changes
```

### Component responsibilities

0. **Exclusive mode/cutover guard:** prevents the legacy `SocialPipeline`/`EngagementPipeline` and growth service from publishing concurrently. Ownership is keyed by `(platform, action_kind)` and carries a monotonically increasing fencing epoch. Transfer atomically sets the key to `draining`, which denies new leases. The worker's final epoch check and transition to durable `sending` occur in one database transaction; if it wins first, transfer waits. Transfer proceeds only when no old-epoch `leased` or `sending` attempt remains—never by expiring a `sending` attempt. A stuck `sending` row becomes manual investigation, not a forced handoff. Only then does transfer increment the epoch/owner. `SOCIAL_GROWTH_MODE` controls every programmatic social write, legacy outbound remains forced off after cutover, and LinkedIn remains manual.
1. **Asset resolver:** joins a finding/topic to an eligible `ContentAsset`, applying type-specific readiness rules and deterministic tie-breaks. It verifies artifact hash/status, URL/canonical, source coverage, claim support, and a short publish-time TTL.
2. **Opportunity collector:** gathers only data permitted by a documented platform use case. Until the data-handling review passes, it uses local/manual inputs and local scoring; Reddit API collection stays disabled until Reddit grants written approval.
3. **Candidate scorer:** deterministically combines audience fit, timeliness, evidence strength, novelty, expected conversation value, destination quality, and policy risk. The LLM may propose component scores but cannot override hard gates.
4. **Angle generator:** produces distinct content angles from one `ContentAsset` without changing factual claims.
5. **Platform writers:** use separate prompts/schemas for owned X/Bluesky originals and the manual LinkedIn draft. Platform user content is never sent to an external model until the platform/model data-handling review passes. Reddit MVP packages contain MindPattern evidence and human-recorded rule notes only; Tayler writes the actual post/comment, and no Reddit writer/critic agent exists in scope.
6. **Validators:** verify claim-to-source support, URL health, platform constraints, prohibited language, disclosure, semantic duplication, community rules, and UTM/campaign fields.
7. **Approval router:** decides which queue/action is allowed using code and configuration, not model prose.
8. **Outbox/scheduler:** atomically leases one immutable, approved content hash and locks the whole `(platform, publication_id)` slot before an external call. It also acquires a short-lived per-platform original-post gate, then reruns exact and semantic duplicate validation against all approved, sending, unknown, and posted variants while that gate is held. This serializes the final duplicate decision across different publications. It claims an idempotency receipt, respects quiet hours/cadence/budget, and records `posted`, `definite_failure`, or `unknown_outcome`. A changed content hash cannot bypass an unresolved earlier attempt for the publication slot. Non-idempotent POSTs are never retried inside a generic HTTP helper after a timeout/connection loss; control returns to reconciliation first.
9. **Platform adapters:** hold credentials and call official APIs. LLM processes never receive tokens or direct posting tools. Reads may use bounded transient retries; non-idempotent writes use a separate no-blind-retry path unless the platform supplies a proven idempotency key.
10. **Manual action recorder:** creates an expiring, content-hashed package and blocks regeneration while it is outstanding. Tayler records `posted`, `edited_and_posted`, `not_posted`, or `expired` plus a URL/ID when available. Because native UI actions cannot be controlled by the gateway, deduplication is explicitly best-effort and the UI warns before any near-duplicate package.
11. **Metric collector:** stores immutable platform snapshots and imports privacy-safe, per-campaign aggregates from Fly using an authenticated cursor. Raw site event rows and anonymous reader IDs stay in `site_events.db`.
12. **Experiment evaluator:** compares content variants and channel cohorts only after a predeclared sample floor. It proposes changes; it does not silently rewrite policy, voice, or cadence.
13. **Operator dashboard:** shows today's queue, evidence, destination, approvals, API budget, errors, removals, manual-action uncertainty, and funnel performance.

## Typed contracts

Use versioned Pydantic models. FastAPI already depends on Pydantic, but importing it as a direct application contract requires adding a bounded direct dependency with owner approval. Every stored record inherits:

```json
{
  "schema_version": 1,
  "id": "type_opaqueid",
  "created_at": "2026-07-10T14:00:00Z",
  "updated_at": "2026-07-10T14:00:00Z"
}
```

IDs use a type prefix and the same opaque-ID length/character rules as attribution fields. Enumerations below are real typed enums, not free-form pipe-delimited strings.

### `Publication` aggregate

`Publication` is the owning aggregate for one planned original/action and the stable source of `publication_id`. It references campaign, asset, active variant, current validation/approval, mode, platform/action, lifecycle state, and an optional active job/manual action. Its row version serializes edits and prevents two variants from becoming active. Opportunities and measurement snapshots have their own lifecycles and do not share the publication state enum.

### `ContentAsset`

```json
{
  "schema_version": 1,
  "id": "asset_01example",
  "created_at": "...",
  "updated_at": "...",
  "asset_kind": "story",
  "artifact_id": "2026-07-10-example",
  "canonical_url": "https://mindpattern.ai/s/2026-07-10-example",
  "no_link_reason": null,
  "artifact_hash": "sha256:...",
  "finding_ids": [123],
  "claim_evidence": [{"claim": "...", "source_url": "https://...", "finding_id": 123}],
  "confidence": "high",
  "readiness": {
    "status": "ready",
    "reason_codes": [],
    "checked_at": "...",
    "expires_at": "...",
    "observed_canonical_url": "https://mindpattern.ai/s/2026-07-10-example"
  }
}
```

`asset_kind` is `story`, `briefing`, `entity`, `arc`, `research`, or `no_link`; kind-specific validators determine required identifiers/evidence.

### `SocialOpportunity`

Required domain fields: `platform`, `action_kind`, target identifiers/URL, `collection_basis`, `data_handling_review_id`, `origin` (`curated`, `owned_mention`, `manual`, `trend`), score components/reasons, recipient cooldown, and expiry. `target_text` is nullable and must remain local unless the referenced data-handling review authorizes the external model provider.

No agent receives a `SocialOpportunity` object directly. A permission-gated serializer produces a separate `ModelSafeInput` DTO containing only owned `ContentAsset` evidence and non-platform metadata by default. Platform text has no field in that DTO unless an active data-handling review explicitly enables a bounded, redacted excerpt; serialization otherwise fails closed.

### `PlatformVariant`

Required domain fields: `publication_id`, `campaign_id`, `asset_id`, `platform`, `action_kind`, exact content, `content_hash`, `canonical_url`, `tracked_url`, source URLs, disclosure/relationship text, goal, prompt/model versions, validation record ID, and approval mode. `tracked_url` is null for no-link content and manual replies.

### `ValidationRecord` and `ApprovalRecord`

`ValidationRecord` binds the exact `content_hash`, asset hash, validator/policy/prompt versions, readiness snapshot, hard-gate results, warnings, and timestamp. `ApprovalRecord` binds `publication_id`, exact `content_hash`, `validation_record_id`, validation hash, approver identity, Slack thread/reference, decision, edits, timestamp, and expiry. An edit produces a new content hash and requires a new validation and approval record.

### `CommunityRuleSnapshot` and `PlatformPolicySnapshot`

Both are immutable, identified records with source URLs/hashes, checked/expiry times, permitted actions, disclosure/link/flair/account requirements, human notes, and reason codes. Reddit rules expire after seven days by default; platform policy snapshots expire before every mode transition and at most every 30 days. Any unknown required permission fails closed.

### `PublishJob`

```json
{
  "schema_version": 1,
  "id": "job_01example",
  "created_at": "...",
  "updated_at": "...",
  "publication_id": "pub_01example",
  "variant_id": "variant_01example",
  "approval_record_id": "approval_01example",
  "content_hash": "sha256:...",
  "platform": "x",
  "state": "scheduled",
  "scheduled_for": "...",
  "next_attempt_at": "...",
  "lease_owner": null,
  "lease_token": null,
  "lease_expires_at": null,
  "publisher_epoch": 3,
  "active_attempt_id": null,
  "row_version": 1,
  "attempt_count": 0,
  "idempotency_key": "post:x:pub_01example:sha256...",
  "cost_budget_cents": 20,
  "last_transition_at": "..."
}
```

Workers claim jobs with one atomic conditional update. Enforce one active slot per `(platform, publication_id)` independent of content hash, plus uniqueness for each exact attempted hash. A worker must possess the current lease token and active publisher fencing epoch to transition or write.

Final duplicate validation is serialized per platform immediately before `sending`. Exact normalized content hashes are unique across non-cancelled publications; substantial-similarity decisions include approved/sending/unknown/posted variants. The short gate releases after the attempt state is durable, but an `unknown_outcome` remains in the duplicate comparison set until reconciled.

Each network try also creates a durable `PublishAttempt` with `claimed`, `sending`, `definite_not_sent`, `unknown_outcome`, `confirmed_posted`, or `reconciled_not_posted`. A crash while still `claimed` (before the durable `sending` transition) may release the receipt and retry after lease recovery. The worker writes `sending` immediately before the network call; any crash, timeout, connection loss, HTTP 5xx, or adapter-unknown response from that state retains the receipt and becomes `unknown_outcome`. Release is allowed only for an adapter-allowlisted response that definitively means the create was rejected before acceptance, or after reconciliation proves no post exists. If the platform cannot reconcile, require manual investigation/cancellation—never an automatic retry.

### `PublishOutcome`, `ManualActionRecord`, and `PerformanceSnapshot`

`PublishOutcome` identifies the job/publication, status, platform ID/URL, response fingerprint, cost, error class, reconciliation state, and observed time. `ManualActionRecord` identifies the expiring **package hash**, actor acknowledgement, declared status, and platform URL/ID when supplied. `final_content_hash` is nullable because a native reply may never be copied back; `final_content_unavailable_reason` is then required. It records but cannot guarantee native-UI behavior. `PerformanceSnapshot` identifies publication/platform post, observation window, captured time, platform metrics, site aggregate revision, engaged readers, new subscriptions, and removal status.

Null means the platform does not supply the metric; it must never be silently converted to zero.

## State machine

Do not mix opportunity, publication, job, manual-action, and measurement states in one enum:

```text
Opportunity: discovered -> qualified | rejected | expired

Publication: planned -> drafted -> validating
  -> needs_revision -> drafted
  -> validated -> awaiting_approval -> approved | rejected | expired
  -> programmatic_queued | manual_packaged
  -> completed | cancelled

Programmatic job: scheduled -> leased
  -> lease_expired_before_sending -> scheduled
  -> sending -> posted
  -> definite_not_sent -> retry_wait -> scheduled | dead_letter
  -> unknown_outcome -> reconciling
     -> posted | reconciled_not_posted -> scheduled | manual_investigation
  -> cancelled

Manual action: packaged -> outstanding
  -> manually_posted | edited_and_posted | not_posted | expired

Measurement: pending -> partially_observed -> complete | unavailable
```

Invariants:

- No variant can reach `approved` without a `ContentAsset` unless it is explicitly classified as `no_link`/no-claim, and all relationship disclosures still apply.
- No programmatic external action occurs before an outbox row, atomic lease, exact-content approval, and receipt claim exist. Native-UI actions are outside that guarantee and use the best-effort manual action record.
- `unknown_outcome` is reconciled against the platform before retry; never assume failure and duplicate-post.
- An expired community-rule snapshot blocks Reddit packaging.
- Editing approved copy invalidates approval and validation.
- Auto-publishing can be disabled globally and per platform without redeploying.
- The legacy and growth publishers cannot both own the same platform/action mode.

## Scoring and routing

Candidate priority score (initial hypothesis):

```text
0.25 audience_fit
+ 0.20 conversation_value
+ 0.15 evidence_strength
+ 0.15 novelty
+ 0.10 timeliness
+ 0.10 destination_quality
+ 0.05 format_fit
- 0.30 policy_risk
- 0.20 repetition_risk
```

Weights must be configuration, logged with every decision, and revisited only after enough outcome data. Hard gates override the score:

- unsupported or overstated claim;
- broken/unpublished/stale destination;
- missing campaign attribution on a link post;
- duplicate/substantially similar content;
- prohibited automation action;
- missing/expired Reddit community rules;
- missing/expired platform-policy or registered-use-case approval;
- X auto-publish candidate derived from a trend, breaking/current-event trigger, or automated trend detector (route to human/manual instead);
- any AI-generated or programmatic reply adapter (out of scope for this harness regardless of approval state);
- Reddit API/business use without written Reddit approval;
- platform user content headed to an external model without a passed data-handling review;
- missing commercial/founder relationship disclosure where the platform/context requires it;
- recipient/community cooldown violation;
- exhausted API budget;
- active kill switch;
- any unresolved prior attempt for the same `(platform, publication_id)`, even if an edit changes the content hash/idempotency key.

## Safety, security, and platform integrity

- Store credentials only in the existing Keychain/environment mechanism. Never include secrets in prompts, drafts, logs, Slack messages, or database snapshots.
- Treat all platform content, subreddit rules, bios, usernames, and linked pages as untrusted input. Strip or delimit instructions before supplying them to a model; platform text can never change tool access or policy.
- Do not send platform user content to an external model merely because it is public. Require a recorded platform/provider data-handling review; otherwise keep the content local and the reply human-written.
- Use allowlisted official API hosts and fixed adapter methods. Never let a model choose an arbitrary URL for an authenticated request.
- Cap response sizes, timeouts, read retries, and per-run cost. Split read and write HTTP helpers: non-idempotent creates never receive blind timeout/connection/5xx retries.
- Disable automated likes, follows, votes, DMs, subreddit cross-posting, and unsolicited replies.
- Log approval identity, exact content/validation hashes, community/platform policy versions, registered use-case review, prompt/model versions, and exact final content.
- Keep a global `MP_DISABLE_OUTBOUND` switch and add `SOCIAL_GROWTH_MODE=off|shadow|approval|canary|live`.
- Route every **programmatic** post and other external action through one outbound gateway. The MVP gateway rejects all follow/unfollow actions and has no X/Bluesky reply, Reddit publish, or LinkedIn publish method. Native-UI actions are recorded after the fact and remain explicitly outside the kill switch/receipt guarantee.
- Store raw campaign events for 180 days by default, then retain only non-identifying aggregates; make this retention configurable and owner-approved. Continue to honor analytics opt-out.
- For Reddit, fail closed on all API collection until Reddit grants written approval for this exact business-adjacent use. If granted, store the minimum content/metadata, record permitted retention, and propagate deletions as the approval/terms require.
- Before X outbound changes, confirm the app's registered use case, account automation label/disclosure, responsible operator link, and current policy snapshot. Require explicit owner confirmation before billing/auto-recharge, but owner approval never substitutes for platform approval.
- Cut over by platform/action: disable the legacy runner branch before enabling its growth-service replacement, migrate or cancel legacy pending rows, and enforce one database-backed active-publisher lease.

## Measurement plan

### North-star and supporting metrics

**Weekly leading north-star:** unique qualified social readers, deduplicated by valid `anon_id` across all social publications in a fixed Monday 00:00 through next Monday 00:00 `America/New_York` reporting week.

A `qualified publication-reader instance v1` is one valid `anon_id` + `publication_id`, evaluated over the 24 hours starting at that reader's first attributed content view, with at least one of:

- scroll depth of 75% or more;
- a second distinct MindPattern content path within 30 minutes;
- a related, source, or outbound-evidence click.

Exclude empty anonymous IDs, `agent_hit` traffic, invalid/expired campaign IDs, and known internal test campaigns. A person with one or more qualifying publication instances counts once in the weekly north-star; the instances remain a supporting content-level metric. Version any future definition change and never compare across versions without recomputing history.

Report two lagging outcomes separately, only for mature cohorts:

- **new attributable subscribers:** the subscription provider confirmed a newly created contact after a valid last-touch social attribution;
- **30-day retained readers:** a qualified reader returns for a new content view 7–30 days later. Do not report a cohort until its full 30-day window closes.

Supporting metrics:

- conversation rate: posts with at least one non-owner substantive reply / posts;
- sampled reply quality: weekly human rubric over specificity, usefulness, evidence, and authenticity; target-author likes/replies are context, not an optimization target;
- qualified click-through rate by platform, pillar, destination, and variant;
- engaged-session rate after a social click;
- social-to-subscribe conversion;
- 7-day and 30-day return rate using the existing resettable anonymous ID;
- new-subscriber source/campaign distribution;
- approval, edit, rejection, and manual-time rates;
- content freshness and duplicate-block rates;
- API cost per engaged reader and per subscriber;
- Reddit upvote rate, comment quality, removal rate, and moderator feedback;
- policy incident, report, mute, block, and negative-feedback rates where available.

### Baseline, guardrails, and decision rules

Instrument the funnel, freeze the metric definitions and major conversion surfaces, and only then collect a two-week baseline. Do not use traffic gathered while the CTA, homepage promise, attribution, or engaged-reader definition is changing as the comparison cohort.

Non-negotiable launch guardrails:

- 100% of published link posts pass the exact-destination/evidence gate from the first live post.
- Zero account warnings, spam enforcement events, automated follows/likes/votes, or unapproved reply automation.
- Every Reddit removal receives a human reason review; any spam warning or ban pauses the channel.
- At least 95% of programmatic publications receive all eligible metric snapshots.
- X spend remains below the owner-approved cap; auto-recharge remains off unless separately approved.
- No scale decision is based on impressions, follower count, owner rejection rate, or upvote rate alone.

Start experiments with only two pillars—`claim/evidence/take` and `agent failure autopsy`—on one channel at a time. Gather at least eight genuinely comparable original posts before a directional decision. Compare medians and owner minutes, show every raw observation, and label the result exploratory; a small account will rarely support confident causal claims in 90 days.

Initial decision hypotheses, to approve after baseline:

- scale a series only when median qualified readers per owner hour is at least 25% above that channel's stable baseline and no safety guardrail worsens;
- pause/rework a series after eight comparable posts produce neither a qualified reader nor a substantive conversation;
- never compare raw engagement rates across platforms with different denominators or metric availability.

Absolute traffic, conversion, retention, and Reddit upvote targets should be set at the day-30 baseline review, not invented in advance.

## 30/60/90-day operating plan

### Days 1–30: make traffic measurable and earn a voice

- Confirm target reader, account identity, voice, time budget, X budget, automation modes, platform registered use cases, and data-handling permissions.
- During days 1–14, fix asset resolution, campaign attribution, aggregate export, share-event/URL behavior, story subscribe CTA, and homepage promise.
- Freeze `qualified social reader v1`, attribution v1, and major conversion surfaces before collecting a baseline.
- Build the relationship/community registry manually.
- Run the existing Bluesky pipeline in shadow mode; reconnect X only in shadow mode.
- During days 15–30, launch a restrained Agentic Evals series manually and collect the two-week stable baseline while recording owner time and all outcomes.
- Test only the first two content pillars; activity counts are ceilings, not quotas.
- No Reddit automation. Observe communities, contribute manually, and record dated rules.

**Day-30 gate:** data can connect one draft and platform post to an exact destination, engaged session, and subscription; no unexplained duplicate, stale-artifact, or uncertain-post behavior remains.

### Days 31–60: automate safe work and deepen conversation

- Enable approval-mode scheduling for Bluesky and X original posts through official APIs.
- Add locally ranked opportunity lists only where the platform use case/data review permits collection.
- Deliver source notes for X/Bluesky conversations; Tayler writes and posts replies natively. No callable reply adapter.
- Generate Reddit manual packages only for communities with current rule snapshots.
- Start one practitioner collaboration per two weeks.
- Add a simple welcome/share loop and measure it.
- Run one exploratory test at a time with at least eight comparable originals; show raw observations and avoid causal claims.

**Day-60 gate:** at least four weeks of attributable outcomes after the frozen baseline, zero policy incidents, and directional evidence—shown with raw observations—that one or more content series produces qualified conversations or readers without increasing owner time disproportionately.

### Days 61–90: canary safe automation and compound what works

- Allow only pre-approved, low-risk Bluesky original formats to auto-publish as a small canary.
- Consider an equally small X **evergreen, non-trend-derived original-post** canary only if X use-case approval/labeling, cost, policy freshness, and unknown-outcome reconciliation are proven.
- Keep all proactive replies, Reddit, and LinkedIn human-triggered.
- Build the Bluesky starter pack and test one community asset or public dataset derived from MindPattern.
- Launch a minimal referral/share experiment for engaged subscribers.
- Stop or redesign pillars that remain below baseline after adequate samples.
- Produce a day-90 channel review and next-quarter decision.

**Day-90 gate:** automation saves measurable operator time without lowering factual quality, conversation quality, conversion, or account safety.

## Proposed repository structure

### `mindpattern-v3`

```text
social/growth/
  models.py                 # versioned typed contracts and enums
  resolver.py               # finding/topic -> published site artifact
  opportunities.py          # collectors and normalized opportunities
  scoring.py                # deterministic ranking and hard gates
  validators.py             # evidence, URL, policy, duplicate, attribution
  router.py                 # approval-mode routing
  outbox.py                 # durable jobs, receipts, recovery
  cutover.py                # exclusive ownership vs legacy social paths
  manual_actions.py         # copy-only packages and acknowledgements
  data_handling.py          # platform/provider use-case review gates
  scheduler.py              # cadence, quiet hours, budgets
  metrics.py                # platform/site snapshots and funnel joins
  experiments.py            # experiment registry and evaluations
  service.py                # orchestration entry point
social/platforms/
  bluesky.py                # adapter around existing BlueskyClient
  x.py                      # adapter around existing XClient
  reddit.py                 # no network methods until written Reddit approval
  linkedin.py               # manual package only
agents/
  x-writer.md
  x-critic.md
  social-opportunity-ranker.md
policies/
  social-growth.json
tests/
  test_social_growth_models.py
  test_social_growth_resolver.py
  test_social_growth_scoring.py
  test_social_growth_validators.py
  test_social_growth_outbox.py
  test_social_growth_routing.py
  test_social_growth_metrics.py
  test_social_growth_integration.py
```

Extend `memory.db` through migrations for campaigns, opportunities, drafts, rule snapshots, publish jobs/outcomes, metric snapshots, and experiments. Reuse `social_posts`, `social_feedback`, `engagements`, and `receipts`; do not create parallel duplicate truth for the same concepts.

Canonical ownership after cutover:

| Concern | Canonical store | Compatibility behavior |
|---|---|---|
| Campaigns, assets, variants, validation, approval, jobs, outcomes | New growth tables in `memory.db` | None; these are the lifecycle truth. |
| Final approved/published copy and voice exemplars | `social_posts`, with a unique nullable `growth_publication_id` | Written once in the same transaction as the terminal growth outcome; never treated as a job queue. |
| Reply/manual engagement history | `engagements`, with a unique nullable `growth_action_id` | Records completed/history state only. |
| Legacy deferred jobs | `pending_posts` | Migrated or cancelled at cutover, then read-only/deprecated. |
| External-action idempotency | `receipts` keyed by publication + exact content hash | One claim path for all programmatic writes. |
| Reader events and anonymous cohorts | production-local `site_events.db` | Only aggregate campaign rows cross into local `memory.db`. |

The migration must backfill stable links where possible, expose a compatibility view for existing dashboards, and enforce uniqueness so a terminal growth outcome cannot be mirrored twice.

### `mindpattern-rabbit-hole`

```text
src/lib/analytics.ts                         # campaign-aware privacy-safe events
src/lib/attribution.ts                       # strict IDs, 7-day last touch, clean shares
src/components/subscribe/story-subscribe.tsx # contextual story CTA
src/components/story/share-button.tsx        # Bluesky/Reddit + accepted share event
src/app/(app)/page.tsx                       # clear promise/start-here path
src/app/(app)/about/page.tsx                  # method, author, provenance
redirect/canonical configuration             # /blog -> /briefings
```

## Implementation plan

Every task below should land behind tests and a disabled-by-default feature mode. Sizes are relative: S (hours), M (1–2 days), L (3–5 days), XL (more than a week or cross-service uncertainty).

1. **Approve product, platform, dependency, and data decisions (S).** Confirm audience/identity/time/budget; obtain or explicitly defer X use-case/automation approval; treat Reddit API access as prohibited pending written Reddit approval; approve retention and any direct Pydantic/Playwright dependencies. Acceptance: every open decision has an owner/platform answer or a fail-closed mode.
2. **Define models, ownership, and migrations first (L).** Implement the base record, enums, all contracts, uniqueness/foreign keys, canonical ownership table, legacy mapping, and migration/backfill plan. Acceptance: an old fixture DB upgrades and every record round-trips; duplicate publication/outcome/manual package constraints fail deterministically.
3. **Define the cross-repository attribution contract (M).** Add strict fields/regexes/caps/enums, `publication_id`, tracked URL, last-touch v1, new-vs-existing subscriber behavior, clean-share rules, opt-out behavior, retention, and sanitization before both analytics sinks. Acceptance: shared contract fixtures pass identically in Python and TypeScript; malicious/PII-like values are rejected before storage or Vercel.
4. **Build the private aggregate analytics boundary (M).** Add bearer-protected, revisioned per-publication plus cross-publication weekly/channel aggregates computed inside production `site_events.db`, a rolling 35-day recomputation/maturation job, and a changed-row cursor; local storage receives no raw anonymous rows. Acceptance: production-side fixtures prove weekly deduplication across two publications, repeated imports are idempotent, late events and time-matured cohorts produce higher revisions, and per-publication/new-subscriber/mature-retention totals reproduce.
5. **Build the type-aware asset resolver (L).** Add deterministic readiness rules, tie-breaks, reason codes, artifact hash, TTL, and publish-time revalidation for every asset kind. Acceptance: fixtures cover each kind and every missing, changed, unpublished, unsupported, degraded, canonical-mismatch, or evidence-deficient state.
6. **Add a site test foundation (M, owner-approved dependency).** Install/configure Playwright or an approved equivalent; keep `pnpm build`/lint. Acceptance: CI can execute desktop/mobile navigation, attribution, subscribe, share, redirect, and canonical checks against a local backend fixture.
7. **Improve site conversion surfaces (L, site repo).** Story CTA, homepage promise/start-here, About/method, closed analytics schema, clean X/Bluesky/Reddit/copy/native shares, and `/blog` redirects/sitemap removal. Acceptance: tagged story -> qualified read -> confirmed new subscription -> aggregate endpoint passes; shared URLs contain no acquisition/opt-out query; one briefing canonical remains.
8. **Isolate every run and platform artifact (M).** Use run IDs/directories or structured returns. Acceptance: parallel runs and stale X/Reddit fixtures cannot cross-read EIC, brief, draft, critic, or expeditor artifacts.
9. **Split read retry from non-idempotent write and build the leased outbox (XL).** Add atomic SQL claims, leases/versions, publication-slot locks, a serialized per-platform final duplicate gate, durable attempt states, exact hashes, receipts with explicit release rules, no-blind-retry creates, reconciliation, retry scheduling, and dead letters. Acceptance: concurrent workers across the same or different publications, edited/similar variants, and crash/timeout/5xx fault injection never issue a second create before reconciliation; `claimed` vs `sending` recovery follows the specified protocol.
10. **Make approval durable and exact (M).** Persist approver, Slack reference, content/validation hashes, edits, versions, and expiry. Acceptance: any content/asset/policy change invalidates the approval and blocks leasing until revalidated/reapproved.
11. **Build gateway and fenced-ownership scaffolding without activating cutover (L).** Patch legacy and growth paths so the final epoch check and durable `sending` transition are one transaction; add `draining`, lease renewal, no-new-lease, wait-for-zero-sending, transfer, and one gateway/kill switch. Acceptance: a transfer cannot complete while an old worker is leased/sending, a worker loses if draining wins first, and LinkedIn/replies/follows/Reddit have no callable programmatic publish method. Legacy ownership remains active until task 20.
12. **Implement deterministic validators and expiring policy/data snapshots (L).** Acceptance: table-driven tests cover every hard gate, X trend-derived auto block, disclosure, platform approvals, data-to-model permission, budgets, cooldowns, and mode transition.
13. **Build copy-only manual packages (M).** Reddit rules/evidence checklist, LinkedIn copy/media, and X/Bluesky conversation source notes; no generated reply from platform user content without the data review. Acceptance: outstanding/posted content hashes block repeat packages, edits are recorded honestly, and the UI states that native actions are outside gateway guarantees.
14. **Reconnect X originals in shadow mode only (M).** Add original-post writer/critic/policy/config around a corrected write adapter. Acceptance: packages include registered-use-case/policy/cost checks; trend/current-event candidates cannot be auto-eligible; zero outbound calls.
15. **Move Bluesky originals to the leased outbox in shadow mode (M).** Acceptance: mocked API proves facets, scheduling, approval hash, receipts, outcomes, reconciliation, and metrics without changing legacy live behavior.
16. **Add bounded, permitted opportunity lists (M).** Start with manual/local inputs; add API collectors only after platform/data approvals. Acceptance: local ranking is deterministic, recipient cooldowns apply, prompt injection cannot change tools/policy, and no platform text reaches an unauthorized model.
17. **Add metric collectors and funnel joins (L).** Acceptance: 1h/24h/72h/7d platform snapshots remain immutable, missing metrics stay null, at least 95% of eligible programmatic publications receive all snapshots, and aggregate cursors join reproducibly on `publication_id`.
18. **Add an exploratory experiment review (M).** Acceptance: it enforces one channel/two initial pillars/eight comparable originals, shows raw observations and owner time, labels conclusions exploratory, and proposes rather than applies changes.
19. **Shadow for two weeks after metric freeze (M operational).** Acceptance: every would-be programmatic action has asset evidence, exact validation/approval route, policy/data snapshot, estimated cost, and human quality label; zero outbound actions.
20. **Per-platform cutover into approval launch, then separate canary decision (M operational).** After validators, adapters, and shadow evidence pass, mark the old `(platform, original)` epoch draining, stop new leases, reconcile every old `sending` attempt, migrate/cancel unsent pending rows, then transfer the fence and run approved X/Bluesky originals. A later signed decision must name platform, evergreen format, cap, current policy/use-case evidence, rollback trigger, and review date. Acceptance: transfer never expires an old sending attempt, only one platform/action is moved at a time, rollback performs a new drain/epoch transfer, and no canary is possible through configuration alone before its record exists.

Dependency order: `1 -> 2 -> (3, 5, 8, 9, 10)`, `3 -> (4, 6) -> 7`, `(8, 9, 10) -> 11 -> 12`, `(5, 12) -> (13, 14, 15, 16)`, `(3, 4, 7, 14, 15, 16) -> 17 -> 18 -> 19 -> 20`.

## Testing and verification

### Unit tests

- typed schema validation and version upgrades;
- scoring math and logged reason codes;
- claim/source support and destination gates;
- semantic duplicate checks within and across platforms;
- community-rule expiry and disclosure;
- action-to-approval-mode matrix;
- base-record, foreign-key, ownership, lease, and uniqueness constraints;
- cadence, quiet hours, and budget ceilings;
- tracked/canonical/share URL behavior, attribution expiry, and privacy cleaning before both analytics sinks;
- immutable metric snapshots and null handling;
- experiment sample floors.

### Integration and failure-injection tests

- mocked Bluesky and X success, 400, 401, 403, 429, 5xx, timeout, and connection reset;
- assert non-idempotent creates are called at most once on timeout/connection loss while reads retain bounded retries;
- two concurrent workers cannot lease or publish the same exact content;
- an edited content hash cannot bypass an unresolved `(platform, publication_id)` attempt;
- two different publications with exact or substantially similar variants cannot pass the serialized final duplicate gate concurrently;
- crash before receipt, after receipt/before request, after request/before response, and after response/before commit;
- durable `claimed`/`sending` attempt recovery and receipt-release rules are asserted for each crash point;
- platform reconciliation after `unknown_outcome`;
- stale output from a prior run/platform cannot be consumed;
- approval edit invalidates validation and requires re-approval;
- legacy and growth services cannot own the same platform/action; cutover migrates/cancels pending rows;
- drain/check race tests prove either the worker atomically reaches `sending` and transfer waits, or draining wins and the worker cannot call the API;
- global and per-platform kill switches prevent all network writes;
- no callable X/Bluesky reply, Reddit publish, LinkedIn publish, or follow method exists in MVP;
- expired platform/use-case/data-handling snapshots fail closed;
- malicious content/rule text cannot alter tool access, destination, credentials, or policy;
- only `ModelSafeInput` can cross the external-model boundary; unauthorized `target_text` serialization fails;
- end-to-end tagged click -> story event -> subscription success -> campaign dashboard.
- late site events and time-matured 30-day cohorts replace lower aggregate revisions without importing raw reader rows.

### Browser checks

- tagged social URL opens the exact supporting story;
- OG card, title, description, and canonical URL are correct;
- contextual subscribe works on desktop/mobile and preserves permitted campaign fields;
- share controls work for X, Bluesky, Reddit, native share, and copy; all shared URLs strip acquisition and opt-out parameters;
- About/methodology and AI provenance are understandable;
- homepage promise and start-here path are visible above the archive.

### Rollout checks

- `off`: no candidate generation or outbound work;
- `shadow`: full pipeline and cost estimation, zero approvals/API writes;
- `approval`: every action requires the configured human step;
- `canary`: only a separately signed, allowlisted evergreen original format, platform, window, and daily cap; X trend/current-event candidates remain manual;
- `live`: still subject to budgets, hard gates, receipts, and kill switches.

Re-read and snapshot current platform policies, registered use cases, account disclosure/labeling, and data-handling terms before every transition. An expired or changed snapshot blocks the transition.

Rollback is configuration-first: set mode to `off`, preserve queued/audit data, cancel unclaimed jobs, and never delete already-published content automatically.

## What not to build yet

- A generic “AI social agent” that chooses its own goals or tools.
- Browser automation for X or Reddit.
- Automatic Reddit posts/comments.
- Reddit API collection before written Reddit approval for the exact business use.
- Model-generated X/Bluesky/Reddit replies from platform user content before platform/provider data permission is documented.
- Unsolicited automatic X replies, DMs, likes, or follows.
- Cross-platform copy-and-paste syndication.
- A custom Bluesky feed generator before ordinary community participation proves demand.
- A large rewards/referral system before readers demonstrate repeat engagement.
- Paid promotion before organic content and landing-page conversion identify a genuine winner.
- Follower-growth hacks, engagement exchanges, purchased accounts, or coordinated inauthentic behavior.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| More posting creates more noise, not trust | Quality floor, content pillars, no-link value ratio, conversation metrics, kill weak series. |
| AI drafts sound polished but inauthentic | Founder examples, manual replies, edit-memory, platform-native prompts, rejection tracking. |
| Claims overstate source evidence | Structured `claim_evidence`, source validator, destination readiness gate, human approval. |
| Automation triggers account enforcement | Official APIs only, written use-case approval where required, account disclosure/labeling, expiring policy snapshots, conservative ceilings, no prohibited actions. |
| Reddit communities reject promotion | Manual publish, dated community registry, text-first contribution, disclosure, removal learning. |
| X costs run away | Per-job estimate, monthly ceiling, usage collector, no auto-recharge without approval, kill switch. |
| Duplicate posts after network ambiguity | No-blind-retry create adapter, leased transactional outbox, receipts, `unknown_outcome`, reconcile-before-retry. |
| Legacy and growth publishers both act | Per-action cutover record, one active-publisher lease, migrated/cancelled legacy pending jobs. |
| Platform content is improperly sent to a model | Platform/provider data-handling review, local scoring by default, retention/deletion contract, no external-model target text until allowed. |
| Native manual posting escapes the kill switch | No automation claim: expiring content-hashed packages, after-the-fact status/URL, duplicate warning, explicit best-effort label. |
| Traffic arrives but does not convert | Exact landing pages, contextual CTA, campaign attribution, engaged-reader north star. |
| Metrics reward sensational content | Track qualified reading, returns, subscriptions, negative feedback, and claim quality—not impressions alone. |
| Prompt injection through social content | Treat content as data, fixed tools/hosts, deterministic gates, no model-held credentials. |

## Open decisions requiring owner input

1. Are the X, Bluesky, and Reddit accounts Tayler's founder accounts, MindPattern brand accounts, or a mix? This spec recommends founder-led accounts at the start.
2. Is the primary reader “AI agent builders/operators,” or should the first niche be broader/narrower?
3. How many minutes per weekday can Tayler reliably spend on replies and approvals? The plan assumes 30–45 minutes.
4. What monthly X API hard cap is acceptable? The launch recommendation is a small test budget with auto-recharge off.
5. Does Tayler want to request written Reddit approval for this business-adjacent data use? Until Reddit approves it, the harness has no Reddit API collector or publisher.
6. Should `The Ramsay Research Report` remain the email brand, or should it become the MindPattern briefing?
7. Which welcome automation is active beyond the confirmed Resend audience insertion? Attribution v1 remains in privacy-safe site events rather than placing campaign data beside email in Resend.
8. What are the current baseline visitors, engaged sessions, subscriber conversion, open rate, and returning-reader rate? Production data was intentionally not accessed.
9. Which 3–5 Reddit communities does Tayler already participate in authentically, and which additional communities are observation-only?
10. Is the owner willing to publish occasional first-person failures and uncertainty? That is likely to differentiate the account more than polished summaries.
11. Does this plan intentionally supersede the existing repository runbook rule requiring explicit owner approval for every outward action? The recommended answer is “not yet”: preserve it through shadow and approval modes, then approve a narrowly defined original-post canary separately.
12. Does the current X developer app's registered use case cover the proposed original-post and read operations, and will the account use the required automation disclosure/label and responsible-operator link?
13. Which external model/provider settings are approved to receive platform user content, if any? Default is none; use local ranking and human-written replies.
14. Is 180-day raw privacy-safe event retention acceptable, and is adding a direct Pydantic dependency plus Playwright to the site approved?

## Evidence gaps and assumptions

- No production analytics, subscriber records, account-level platform analytics, API balances, credentials, or private messages were accessed.
- No live post was created and no external configuration was changed.
- Direct Reddit discussion sampling was unavailable through the configured local research backend; official Reddit policies/business guidance and indexed public material were used instead.
- Current X/Reddit/Bluesky pricing, access, developer terms, and policy can change. Expiring snapshots and mode-transition reviews are mandatory.
- Cadence ceilings and experiment decision rules are starting hypotheses, not growth formulas. Establish the baseline only after instrumentation/definition freeze.
- The founder-led identity recommendation is an inference, not a confirmed product decision.

## Primary external sources

- MindPattern, [live homepage observed during the 2026-07-10 audit](https://mindpattern.ai/)
- X, [Automation rules (updated April 2026)](https://help.x.com/en/rules-and-policies/x-automation)
- X, [Developer Policy](https://docs.x.com/developer-terms/policy)
- X, [Developer Guidelines](https://docs.x.com/developer-guidelines)
- X, [Account behavior rules and best practices](https://help.x.com/en/rules-and-policies/x-rules-and-best-practices)
- X, [Conversations recommendations](https://help.x.com/en/resources/recommender-systems/conversations-recommendations)
- X, [Organic best practices](https://business.x.com/en/basics/organic-best-practices)
- X, [API pay-per-use pricing](https://docs.x.com/x-api/getting-started/pricing)
- Reddit, [Responsible Builder Policy (updated June 2026)](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)
- Reddit, [Developer Terms](https://redditinc.com/policies/developer-terms)
- Reddit, [Spam policy](https://support.reddithelp.com/hc/en-us/articles/360043504051-Spam)
- Reddit, [Devvit rules](https://developers.reddit.com/docs/devvit_rules)
- Reddit for Business, [How publishers can win community engagement](https://www.business.reddit.com/learning-hub/articles/how-publishers-can-win-reddit-community-engagement)
- Reddit for Business, [How to measure organic engagement](https://www.business.reddit.com/learning-hub/articles/measure-reddit-organic-engagement)
- Bluesky, [Community Guidelines](https://bsky.social/about/support/community-guidelines)
- Bluesky, [Developer Guidelines](https://docs.bsky.app/docs/support/developer-guidelines)
- Bluesky, [Introducing starter packs](https://bsky.social/about/blog/06-26-2024-starter-packs)
- Bluesky, [Custom feeds documentation](https://docs.bsky.app/docs/starter-templates/custom-feeds)
- Buffer, [Replying to comments and engagement: analysis of nearly two million posts](https://buffer.com/resources/replying-to-comments-boosts-engagement/)
- Buffer, [Consistent posting study](https://buffer.com/resources/consistent-posting-study/)
- Metricool, [2026 social media study methodology and findings](https://metricool.com/press-release-2026-social-media-study/)
- Pew Research Center, [News influencers' use of Bluesky and X](https://www.pewresearch.org/short-reads/2025/05/29/bluesky-has-caught-on-with-many-news-influencers-but-x-remains-popular/)
- Kit, [Creator Network recommendations and list growth](https://kit.com/resources/blog/how-to-use-paid-recommendations)
- beehiiv, [Newsletter referral program overview](https://www.beehiiv.com/features/referral-program)

## Repository evidence index

### `mindpattern-v3`

- `run-launchd.sh`
- `run.py`
- `social/pipeline.py:SocialPipeline`
- `social/eic.py:select_topic`
- `social/writers.py:PLATFORMS`
- `social/writers.py:_build_writer_agent_prompt`
- `social/critics.py:review_draft`
- `social/engagement.py:EngagementPipeline`
- `social/posting.py:XClient`
- `social/posting.py:BlueskyClient`
- `social/approval.py:ApprovalGateway`
- `policies/social.json`
- `memory/social.py`
- `memory/events_db.py:ALLOWED_EVENTS`
- `dashboard/routes/site_analytics.py:_summary`
- `preflight/reddit.py`
- `tools/reddit-fetch.py`
- `agents/bluesky-writer.md`
- `agents/bluesky-critic.md`
- `agents/linkedin-writer.md`
- `agents/linkedin-critic.md`

### `mindpattern-rabbit-hole`

- `PRODUCT.md`
- `src/app/(app)/page.tsx`
- `src/app/(app)/s/[slug]/page.tsx`
- `src/app/og/story/[slug]/route.tsx`
- `src/components/story/share-button.tsx`
- `src/components/subscribe/subscribe-band.tsx`
- `src/app/api/subscribe/route.ts`
- `src/lib/analytics.ts`
- `src/app/sitemap.ts`
- `src/app/llms.txt/route.ts`
- `public/research/agentic-evals/index.html`
- `docs/specs/2026-06-26-rabbit-hole-rebuild-spec.md`
- `docs/runbooks/2026-07-02-rabbit-hole-new-feature-discovery.md`

## Approval gate

Implementation must not begin from this draft alone. The owner should first answer the open decisions, adjust the provisional targets, and explicitly approve the implementation plan and the cross-repository scope.
