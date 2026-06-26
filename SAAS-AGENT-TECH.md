# How SaaS Platforms Use Agents — Technical Reference

**Compiled:** 2026-04-13
**Scope:** How every major SaaS agent platform actually works. Architecture, build path, runtime behavior, failure modes. No pricing, no ARR, no logo counts.

---

## The universal pattern

Every platform in this document implements the same loop:

**declare tools → retrieve grounding → planner picks tools → execute against a deterministic substrate → emit audit trail → escalate if confidence or sentiment trips a guardrail**

The differentiators are:
1. How far the "execute" layer reaches (KB lookup → CRM write → third-party API → monetary action → code commit)
2. Who gets to see inside the loop (typed SDK vs. opaque UI)
3. How tools are bound (declarative metadata vs. UI-only vs. code)
4. What the escape hatch to non-native systems looks like (MCP, OpenAPI, custom code)

---

## 1. Salesforce Agentforce

### Runtime — Atlas Reasoning Engine

Atlas runs a **ReAct loop** on a classical agent stack:
**retrieve grounding → draft plan → evaluate plan → execute actions → check guardrails → generate response**

Components:
- **Planner** converts the user turn into a step-wise plan
- **Action Selector** picks tools
- **Memory** holds conversation state
- **Reflection** re-scores the plan against the goal before executing

Salesforce calls this "System 2" inference-time reasoning — the LLM never streams straight to the user. If the plan scores low, Atlas loops back and re-plans against fresh retrieval. Atlas is model-agnostic (OpenAI, Anthropic, Gemini). All traffic sits behind the **Einstein Trust Layer**: PII masking, zero retention with model providers, toxicity scoring, prompt-injection defense, audit trail.

### Declarative unit — Topics + Actions + Instructions

- **Topic** = classifier bucket (scope + description + instructions). Router picks ONE Topic per turn; Atlas is constrained to Actions attached to that Topic.
- **Instructions** = natural-language guardrails stitched into the system prompt for that Topic.
- **Action** = a typed tool. Five reference types:
  - **Flow** — Salesforce Flow (deterministic write layer)
  - **Apex** — `@InvocableMethod` class; `InvocableVariable` inputs/outputs become the tool schema Atlas sees
  - **Prompt Template** — a second LLM call with structured inputs
  - **External Service** — upload an OpenAPI spec → auto-generated REST action
  - **MuleSoft** — Agentforce Connector surfaces API Catalog endpoints

**Hard ceiling: 15 Topics per agent × ~15 Actions per Topic.** Enterprises that outgrow this build multiple agents and route via A2A.

### Grounding — Data Cloud hybrid search

Unstructured content → chunked → mapped to a **UDMO** (Unstructured Data Model Object) → embedded → **Search Index** bound to a Data Space + DMO. Three index types: **vector**, **keyword**, **hybrid (BM25 + dense vector fused)**. Hybrid is default — keyword alone misses semantics, vector alone misses SKUs and jargon. Atlas inserts a `RetrieverInvocation` action into the plan; chunks land in the prompt with citations back to source records.

### Write layer — bound by Salesforce governor limits

The LLM never mutates records directly. It calls a Flow or Apex invocable, which runs inside a normal Salesforce transaction and is bound by the same limits:
- **10-second Apex CPU per transaction**
- **SOQL queries: 100**
- **DML statements: 150**

One agent turn cascades through record-triggered flows, process builders, and validation rules — all against the same budget. This is the #1 cause of production failures.

### Build path

Setup → **Agentforce Agents → New Agent** → template (Service / Sales / Custom) → **Agent Builder** opens.
1. Add Topic → Classification Description, Scope, Instructions
2. Add Action → pick reference type (Flow / Apex / Prompt Template / External Service / MuleSoft)
3. Attach a Knowledge article set or Data Cloud Retriever to the Topic
4. **Preview** → **Simulate** (no writes) or **Live Test** (real writes)
5. **Plan Tracer** shows every event per turn: Topic selected, Instructions injected, Actions called with inputs, retrieval results, reasoning trace, guardrail verdicts

### Source control

Metadata types (Winter '25, API v60+): `Bot`, `GenAiPlanner`, `GenAiPlugin` (Topic), `GenAiFunction` (Action), `AiEvaluationDefinition` (regression test).
**Agentforce DX** + `sf` CLI → git → sandbox → prod. Change sets work but miss dependencies.

### Deployment trace — "bump this account to Gold"

1. Classifier routes to Topic `Loyalty_Management`
2. Retriever hits Data Cloud hybrid index on `Account__dlm` + Knowledge UDMO → pulls eligibility rules
3. Planner emits: `[check_eligibility → update_tier → notify_customer]`
4. Apex `LoyaltyEligibilityService.check()` runs SOQL on Order history
5. Flow `Update_Loyalty_Tier` writes `Account.Loyalty_Tier__c = 'Gold'`
6. Apex → External Service → POST to internal Kafka proxy (OpenAPI-registered)
7. Flow → Marketing Cloud Connect templated email
8. Guardrail check → response with citations

Admin wired: one Retriever, one Apex class with three `@InvocableMethod`s, two Flows, one OpenAPI spec, one Topic with four Actions, ~300 words of Instructions.

### Newer pieces

- **Agent Script (GA 2026)** — declarative DSL. YAML-ish key:value with strict indentation (2 spaces or 1 tab, never mixed). Supports `if/else`, `transition`, variable compare, `select subagent` / `select action`. Replaces pure-NL Topics where determinism matters. Source-controllable in VS Code with syntax highlighting + validation.
- **Agentforce Voice** — runs over SIP. Pipeline: **STT → Atlas → TTS with barge-in.** Same Topic/Action loop, voice-shaped turn boundaries. SIP signaling region configurable for latency.
- **A2A (Agent2Agent)** — Google-originated cross-vendor protocol. Handshake exchanges **agent cards** (capability manifests), establishes a task session, passes structured messages. **MCP = agent↔tool; A2A = agent↔agent** — orthogonal protocols.

### What breaks

- Apex CPU limit exceeded (#1 failure)
- 15/15 Topic/Action ceiling
- Hallucination 3–27% — missing fields on retrieved records = fabrication; tight Topic scope + Knowledge grounding drops it to 3–5%
- Classifier picks wrong Topic when descriptions overlap
- **Latency 4–10s per turn** — Atlas doesn't stream; it plans then executes. Voice deployments feel this worst.

---

## 2. HubSpot Breeze

### Runtime

**No proprietary model.** Breeze is an orchestration layer on top of OpenAI (GPT-4.x) and Google. HubSpot wraps them behind its permissions plane — same CRM ACLs apply to agent calls.

**Breeze Intelligence** is the data layer (built on the Clearbit acquisition, Nov 2023, launched Sept 2024). Reactive enrichment + identity resolution + buyer intent:
- **Enrichment** — ~40 firmographic/demographic/technographic attributes against HubSpot's company graph
- **Identity resolution** — reverse-IP joins anonymous web visits to companies (domain, VID, IP, timestamp, URL path per hit)
- **Buyer intent** — signals surfaced on the company record

### Declarative unit — Breeze Studio

An agent is four things: **Inputs + Instructions + Knowledge + Tools.**

**Tools** come in three types:
- **Get data** — CRM search, web search, HubSpot object lookup
- **Generate** — bounded LLM completion
- **Take action** — mutations (create/update record, publish content, set ticket/deal stage). Each has a **"Review before running this tool"** toggle. Off = fully autonomous.

Under the hood, tools are **HubSpot custom workflow actions exposed into agent context** — agents and workflows share the same permission surface.

### Knowledge Vaults

Each agent has a vault. Ingestible sources:
- Native HubSpot objects (KB, pages, blog posts)
- **URL crawl** — one seed URL + "Import related URLs" walks the domain (~1,000 page practical ceiling)
- **File uploads** — `.pdf`, `.docx`, `.html`, `.txt`, `.md`
- **CRM property bindings** passed at runtime

The agent decides *answer from vault* vs *call a tool* vs *hand off* using a confidence score on retrieval + LLM self-assessment. **The threshold is NOT user-tunable as a numeric value.** Control is via escalation rules and keyword filters only.

### Write layer

Action tools route through HubSpot's native workflow actions (write to HubSpot objects, ticket/deal state, content). For anything non-native, use MCP.

### Escape hatch — MCP

HubSpot ships two MCP servers:
- **Remote MCP Server** — external LLM clients (Claude, etc.) read/write CRM through HubSpot auth
- **Developer MCP Server** — local CLI for scaffolding

Inside Breeze Studio, **MCP Client** lets agents consume third-party MCP servers (Zapier, custom URLs) as tools. **This is the only sanctioned way to reach Shopify, Stripe, or anything not native to HubSpot.**

### Build path

1. Breeze → Breeze Studio → Agents tab → **Configure**
2. **What this agent knows** → **Add knowledge** → vault → KB/blog/pages/URL/files
3. **What this agent can do** → **Add tool** → Get data / Generate / Take action → review toggle
4. **Instructions** — prompt, tone (Friendly/Professional/Casual/Empathetic/Witty), persona, blocked topics, escalation keywords
5. **Customer Agent:** Deployment → attach to live chat, email, or rule-based bot. Triggers: keyword match, explicit human request, low confidence
6. **Test** in chat preview. Every tool call logged in audit cards.

### Orchestration primitive — Run Agent workflow action

Any HubSpot workflow step can call `AI → Run agent`, pick an agent, pass inputs from the enrollment object, and collect output as either **Text response** or **Structured data** (declared output fields) written back to CRM properties. Primary way Breeze chains into deterministic automation.

### What breaks

- Non-HubSpot KBs second-class (no native Notion/Confluence/Zendesk connector)
- Shallow URL crawler, ~1,000-page ceiling, weak on JS-rendered pages
- Opaque — no exposed system prompt, no numeric confidence threshold
- Channel lock-in (Prospecting Agent: HubSpot only, no LinkedIn, no phone)
- No first-class Shopify/Stripe write tools — route via Operations Hub or MCP

---

## 3. Intercom Fin

### Runtime — Tasks + Data Connectors

Fin is built on two primitives:
- **Data Connector** — configured API call to an external system (Shopify, Salesforce, Stripe, Jira, custom internal tool). Fin decides at runtime when to invoke it.
- **Task** — multi-step workflow that chains Connectors, performs identity verification, waits on webhooks, branches on business logic.

### Action types

Documented action types the agent can take:
- Retrieve live customer data
- Process refunds
- Update subscriptions
- Change account properties
- Translate backend error codes into plain language

### Deployment pattern

Fin sits *on top of* existing stacks. Lightspeed runs Fin over Zendesk (ticketing) + multiple Salesforce instances (CRM/entitlements) + overlapping ERPs + siloed KBs **without replacing any of them**. Anthropic runs Fin over its free-tier Claude account system for subscription management and billing lookups.

### Escalation logic

Confidence + sentiment + explicit guardrails. On handoff, Fin emits a **structured summary** so the human doesn't restart the conversation.

### Write layer

Connectors are the only write path. Any action touching money or state change calls a Connector. **Fin Actions** (Anthropic pilot) extends this to automated refunds — still via Connectors to Stripe.

### Build path

Admin configures Data Connectors (REST endpoints + auth + schema) → defines Tasks as flowcharts combining Connector calls + identity checks + decision branches → attaches Tasks to intents → deploys to the channels (Messenger, email).

---

## 4. Zendesk Resolution Platform

### Architecture — five components

1. **AI Agents** — the conversational runtime
2. **Service Knowledge Graph** — structured KB + ticket history
3. **Actions & Integrations** — tool layer
4. **Governance & Control** — escalation strategies and flows
5. **Measurement** — resolution analytics

### Tool layer — Action Builder

Action Builder (EA April 2025) is a **no-code workflow composer** with prebuilt connectors to Jira, Slack, and Salesforce. Inside a single conversation, an agent can read an order from Salesforce, open a Jira engineering ticket, and post a Slack notification — chained steps inside one agent turn.

### Escalation — strategies and flows

Configurable intents + entity detection + sentiment tracking decide routing. Admins define escalation strategies per intent with thresholds. Copilot mode lets humans stay in the loop — agent drafts replies, pulls KB articles, suggests actions, human reviews.

### Grounding

Service Knowledge Graph pulls from KB articles + historical ticket resolutions. No public hybrid-search toggle like Salesforce's.

### Build path

Admin Center → AI → AI Agents → configure intents → attach Action Builder workflows → configure escalation strategies → deploy to messaging/email channels.

### What the platform does NOT do

Anything outside configured Actions; tickets where sentiment/intent crosses the escalation threshold.

---

## 5. ServiceNow Now Assist + AI Agents

### Declarative unit — "Assists" and AI Agents

An **assist** is a unit-of-work AI task inside a ServiceNow workflow (summarization, drafting, classification). An **AI Agent** is an autonomous worker that chains multiple assists plus tool calls to complete an end-to-end task.

### Ships out-of-the-box

- **ITSM Incident Categorization Agent** — reads new incident, infers category/subcategory and affected CI from caller's assigned assets, routes
- **Post-Incident Review Agent** — auto-generates executive summary, impact, action items from major incident + child records
- **HR agents** — time-off approvals, policy Q&A, onboarding flows

### Autonomy model — human-on-the-loop

Admins set guardrails per action. High-impact actions (create a change request, modify a CI) require explicit approval. Agents escalate when risk thresholds are exceeded.

### Integration layer

Now Platform's flow designer is the substrate. Agents call **Flow Designer flows**, which in turn hit ServiceNow tables and external integrations via IntegrationHub spokes (Okta, M365, Workday, Jira, etc.).

### Post-acquisition stack (as of 2025–2026)

Moveworks, VESA, and ARMS are now inside ServiceNow — so Now Assist + Moveworks share infrastructure.

---

## 6. Moveworks (now ServiceNow)

### Runtime

Employee-facing conversational agent sitting in Slack / Teams / web portal. Parses natural language requests, maps to tasks, executes against ~100 enterprise integrations.

### Concrete task catalog

- **Password reset** in <60 seconds with MFA verification
- **Account unlocks** (Okta)
- **Software access provisioning** (policy-based)
- **Laptop orders** — parses "order a replacement laptop" → checks eligibility/policy → collects missing fields → triggers procurement through **Workday**
- **Device returns**
- **New-hire onboarding flows**
- **Ticket routing** with root-cause suggestion drafted from logs

### Integration layer

Native connectors to Workday, ServiceNow, Jira, Okta, M365, Zendesk, Salesforce, SAP.

### Autonomy model

Fully automated for routine flows (password reset, software provisioning against allowlist). Escalates to human when policy constraints fail or confidence drops.

---

## 7. Microsoft Copilot Studio

### Declarative unit — Topics + Actions

Copilot Studio uses a Topic model (predates Agentforce — originally Power Virtual Agents). Topics are triggered by utterance matching, keyword, or events. Actions inside Topics call:
- **Power Automate flows** (deterministic write layer)
- **Connectors** (1,500+ prebuilt, including SharePoint, SAP, ServiceNow, Workday)
- **Custom code via Azure Functions**
- **MCP servers** (added 2025)

### Pre-built agent templates

- **Employee Self-Service Agent** — answers HR/IT questions and files tickets via SharePoint, Workday, SAP, ServiceNow
- **IT Helpdesk Agent** — resolves tickets with conversational memory, **creates purchase orders for device refresh**, chases manager approvals autonomously
- **Website Q&A Agent**
- **Store Operations Agent**

### Knowledge layer

Agents ingest:
- SharePoint sites
- Dataverse tables
- Public websites (crawl)
- Document libraries (PDF, DOCX)
- Azure AI Search indexes

### Autonomy model

Default is draft-for-approval on actions touching money or external systems. Conversational lookups run fully autonomous. **Autonomous agents** (added late 2024) can run on triggers without a human in the chat — e.g., a new SharePoint doc → agent classifies it → files it in the right Teams channel.

---

## 8. Sierra (Bret Taylor / Clay Bavor)

### Runtime — Agent OS

Sierra's Agent OS orchestrates **structured function calls** against customer-owned systems. Every deployment is a **branded, company-specific agent** — there is no generic Sierra consumer chatbot.

### Build model — custom per customer

Sierra engineers work with each customer to:
1. Define the agent's persona and voice
2. Map every "skill" (function) to a customer backend call
3. Define the escalation matrix
4. Set up evaluation harnesses (Sierra Explorer for deep research / QA)

### Deployment trace — ADT alarm panel

User: *"My alarm panel is beeping"*
1. Agent asks clarifying questions to identify which of **52 panel models** the user owns
2. Diagnoses cause (usually a dead backup battery)
3. **Places an order and ships a replacement itself** via ADT's order system
4. No human touches the ticket

### Sierra Explorer

Deep-research mode that QAs hundreds of thousands of past conversations to find edge cases, policy gaps, and failure modes — feeds improvements back into the agent definition.

### What the agent can't do

Anything requiring judgment outside codified procedures, or cases where identity cannot be verified or a needed system is unreachable. Hand-off is accompanied by a full conversation summary + structured context.

---

## 9. Decagon

### Runtime — Agent Operating Procedures (AOPs)

**AOPs are natural-language workflow definitions** that Decagon engineers translate into bi-directional integration chains. AOPs cover:
- Intent detection
- Required API calls
- Branching logic
- Write actions
- Escalation conditions

### Integration pattern — bi-directional

Decagon wires into Salesforce, Zendesk, Stripe, and customer-specific internal APIs. Write operations are first-class — the agent is configured to mutate, not just read.

### Deployment examples

- **Rippling** — admin asks about employee healthcare enrollment → agent calls Rippling's internal APIs → retrieves the live employee record → answers. Decagon + Rippling defined **75+ routing tags across 12+ products** to route complex cases to subject-matter experts.
- **Substack** — handles refunds and cancellations end-to-end by calling Substack's internal APIs. Also auto-tags and reports feature requests/bugs back into support tooling.
- **Podium** — agent sets business hours, sends bulk messages on the customer's behalf, changes the business name. **Write operations, not lookups.**

### Escalation

Anything outside defined AOPs or requiring human judgment. Escalation includes the AOP trace so the human sees exactly what the agent attempted.

---

## 10. Glean Agents

### Runtime — Plan-and-Execute

Glean's agent engine uses **Plan-and-Execute with branching logic**. Planner emits a step list; executor runs each step calling tools; if a step fails or produces unexpected output, branching logic routes to an alternate path.

### Tool layer — Glean connectors

Glean's strength is its connector catalog — 100+ enterprise apps (Google Workspace, M365, Salesforce, ServiceNow, Jira, GitHub, Slack, Notion, Confluence, Box, Dropbox, Workday). Every connector indexes content AND exposes actions.

### Concrete agents

- **Meeting-notes-to-tracker** — extracts owner, task, due date, status into a table
- **Sales prospect research + outreach drafting**
- **Customer-support triage** — read ticket → search KB → draft response → route escalations
- **Career growth analysis agent** (Zillow)

### Autonomy model

Mostly draft-first for external-facing actions. Internal knowledge operations run autonomously.

---

## 11. Harvey (legal)

### Runtime — Workflow Builder

Harvey's key abstraction is **Workflow Builder** — a no-code designer that encodes a firm's proprietary playbook (e.g., PE deal review, document triage) into reusable multi-step workflows. The agent isn't a generic LLM — it's **the firm's own expertise operationalized**.

### Deployment model

- **Knowledge/innovation leads** at a firm author workflows
- **Associates** execute them on demand against matter documents
- Workflows reference firm-specific precedent libraries and gold-standard templates

### Agentic layer (April 2025)

Multi-step reasoning agents for:
- Antitrust filing analysis
- Cybersecurity review
- Fund formation
- Loan review

An antitrust agent breaks a merger-control question into sub-tasks, pulls matter documents, assembles an intermediate work product.

### A&O Shearman — ContractMatrix

Harvey's productized contract workflow. Tasks: clause comparison against firm precedent, summarization, precedent search, redlining. Drafts redlined `.docx` + rationale.

### What Harvey does NOT do

No autonomous filing, no signing. All output is lawyer-reviewed. Agents surface intermediate outputs with transparency and oversight.

---

## 12. Ironclad Jurist + Spellbook (contract review)

### Ironclad Jurist — three agents

- **Intake Agent** — extracts metadata from third-party contracts, auto-populates launch forms
- **Redlining Agent** — compares versions, proposes edits aligned to a firm-specific **AI Playbook**, outputs a suggestion rationale
- **Conversational Search** — answers questions over the CLM (contract lifecycle management) database

### Spellbook — Word-native

Lives inside Microsoft Word as an add-in. Generates clauses from **2,300+ templates**, benchmarks against market standards, redlines third-party paper in real time.

### Input/output

Counterparty `.docx` in → redlined `.docx` + rationale + extracted metadata out.

### Scope boundary

Explicitly "repetitive, lower-risk work." No autonomous signing. No negotiation authority.

---

## 13. Cognition Devin

### Runtime — planner + code executor + VM

Devin runs inside a sandboxed VM with a full Linux environment, a browser, a code editor, and shell access. Given a task, it:
1. **Plans** a multi-step approach
2. **Codes** — edits files, runs commands, consults docs
3. **Tests** — runs the test suite in the sandbox
4. **Opens a PR** on GitHub with the diff

### Trigger types

- **Sentry crash log arrives** → Devin investigates and opens a fix PR
- **Bug report filed** → reproduces, diagnoses, patches
- **Failing deploy** → analyzes logs and proposes the fix
- **Code review requested** → reviews the PR, leaves comments

### 2025 features

- **PR Resuming** — takes over existing PRs across sessions (context persists in the VM state)
- **Devin Review** — automatic review on every PR
- **Custom runbooks** — structured task templates for repeated workflow patterns

### Integration layer

GitHub, GitLab, Linear, Jira, Sentry, Slack, Notion.

### Autonomy model

Human review at the PR gate — Devin never merges.

### Scope

Tasks that would take a junior engineer 4–8 hours.

---

## 14. Cursor 2.0 / Composer

### Runtime — Composer

**Composer** is Cursor's proprietary **MoE (Mixture-of-Experts) model trained via RL in real codebases**. Most turns complete in <30s. It replaces calls to OpenAI/Anthropic for the hot path; external models remain available as a toggle.

### Agent mode

Default mode in Cursor 2.0. The agent autonomously:
- Explores the codebase (ripgrep, glob, read)
- Reads docs
- Edits files
- Runs terminal commands

### Multi-agent — up to 8 in parallel

Cursor can spawn up to **8 agents in parallel**, each isolated via:
- **Git worktrees** (local)
- **Remote sandbox machines** (cloud)

Each agent works on a separate task, then the developer reviews and merges.

### Autonomy model

Developer in the loop on every accept/reject. No autonomous commits by default; configurable per-project.

### Integration layer

Cursor is editor-native — it reads files via the filesystem, runs commands in the integrated terminal, and talks to git directly. MCP support added 2025 for external tools.

---

## Head-to-head — the technical comparison

| Dimension | Agentforce | Breeze | Intercom Fin | Zendesk | ServiceNow | Copilot Studio | Sierra | Decagon |
|---|---|---|---|---|---|---|---|---|
| **Build model** | Declarative metadata (SDK) | UI-only | UI + Connectors | No-code Action Builder | Flow Designer + templates | Topics + Power Automate | Custom per customer | AOPs + custom integration |
| **Source control** | Agentforce DX + git | None | Connector config versioned | Limited | Flow Designer versioning | Solution-based export | Vendor-managed | Vendor-managed |
| **Reasoning engine** | Atlas (ReAct, not streaming) | OpenAI/Google orchestration | Task engine + Connectors | Custom per platform | Now Assist LLM framework | Azure OpenAI | Proprietary Agent OS | Proprietary |
| **Hard ceiling** | 15 Topics × ~15 Actions | ~1,000-page crawl | None documented | Intent/flow count per plan | None documented | Topic count per agent | None (custom) | None (custom) |
| **Write layer** | Flow + Apex + External Service + MuleSoft | HubSpot workflow actions + MCP | Data Connectors (REST) | Action Builder + Jira/Slack/Salesforce connectors | Flow Designer + IntegrationHub spokes | Power Automate + 1,500 connectors | Customer-owned APIs | Direct bi-directional API calls |
| **Grounding** | Data Cloud hybrid search (BM25 + vector) | Knowledge Vaults (opaque retrieval) | Connector results as context | Service Knowledge Graph | Now Assist Skills + KB | SharePoint + Dataverse + Azure AI Search | Customer-provided corpus | Customer KB + API responses |
| **Escape hatch** | OpenAPI External Service, MuleSoft | MCP Client | Custom Connector | Action Builder custom action | IntegrationHub custom spoke | Custom connector / Azure Function / MCP | Custom integration | Custom AOP |
| **Testing** | Simulate mode + Plan Tracer + `AiEvaluationDefinition` | Chat preview + audit cards | Conversation logs + Task editor | Intent tester + escalation replay | Flow Designer test | Test pane + transcripts | Sierra Explorer | AOP trace replay |
| **Voice** | SIP + STT/TTS with barge-in | None | Fin Voice (alpha) | Via CCaaS partners | ACR + voice channel | Azure Communication Services | Via CCaaS | Via CCaaS |
| **Cross-vendor** | A2A protocol | MCP consume-side | None | None | None | MCP (both sides) | None | None |
| **Biggest breakage** | Apex CPU limit, 15/15 ceiling, 4–10s latency | Opaque confidence, shallow crawl, channel lock-in | Connector auth drift | Action Builder gaps on write ops | Governance complexity | Topic sprawl, sharing model | Vendor dependency | Vendor dependency |

### The legal/ops/coding tools

| Dimension | Harvey | Ironclad / Spellbook | Devin | Cursor Composer |
|---|---|---|---|---|
| **Build model** | Workflow Builder (firm playbook) | Template library + AI Playbook | Custom runbooks | Editor-native |
| **Runtime** | Multi-step agentic reasoning over matter docs | Doc-diffing + clause generation | Sandboxed VM + Linux + browser | MoE model (Composer) + filesystem |
| **Write layer** | Outputs redlined .docx, memos, structured review | Redlined .docx, metadata into CLM | GitHub PRs | Filesystem + terminal + git |
| **Scope** | Legal research, deal review, merger control | Contract review, clause generation | 4–8 hour junior-engineer tasks | Any code change |
| **Autonomy** | Lawyer-reviewed | Lawyer/ops-reviewed | Human at PR gate | Dev accepts/rejects every edit |
| **Integration** | Firm DMS, matter systems | Ironclad CLM, Microsoft Word | GitHub, Linear, Jira, Sentry, Slack | Filesystem, terminal, git, MCP |

---

## Cross-platform patterns worth internalizing

1. **The declarative unit is the real product.** Topics (Agentforce, Copilot Studio), AOPs (Decagon), Tasks (Fin), Workflows (Harvey), Tools (Breeze). Everyone is building the same abstraction: a named, typed, describable unit of agent behavior bound to a tool set.

2. **Write access is the moat.** Read-only agents all look the same. The platforms that reach into Shopify/Stripe/Workday/GitHub are the ones customers are actually paying for. The escape hatch matters: MCP (HubSpot, Copilot Studio), OpenAPI External Service (Agentforce), custom Connectors (Fin, Decagon), IntegrationHub spokes (ServiceNow), Power Automate (Copilot Studio).

3. **Escalation is always confidence + sentiment + guardrails.** Never rule-based alone. Every mature platform accepts that the agent won't always know — the platform's job is to hand off cleanly.

4. **"Human on the loop" beats "human in the loop"** in the mature deployments. Admins set per-action guardrails; the agent runs autonomously within them. Copilot Studio, ServiceNow, Moveworks all default to this.

5. **Every mature agent emits an audit/handoff summary** so humans don't restart the conversation. This is table stakes now.

6. **Source control is the dividing line between engineer platforms and marketer platforms.** Agentforce DX + git + metadata types = engineer platform. Breeze UI-only = marketer platform. Copilot Studio sits in the middle with solution export. Fin/Sierra/Decagon are vendor-managed (no customer-side source control).

7. **The planner is almost never streaming.** Atlas, Devin, Copilot Studio — they all plan-then-execute. This is the latency floor: 4–10s per turn is normal. Voice deployments feel it most.

8. **Hard ceilings reveal architectural choices.** Agentforce's 15/15 Topic/Action limit and Breeze's ~1,000-page crawl ceiling are visible evidence of where their back-end scalability stops. Enterprise deployments route around these via multi-agent patterns (A2A for Agentforce, Operations Hub for Breeze).

9. **MCP is winning as the cross-vendor tool protocol.** HubSpot ships two MCP servers. Copilot Studio is MCP-native. Cursor added MCP. Agentforce announced A2A (agent↔agent) but still uses typed SDKs for agent↔tool. The protocol war is: **MCP for tools, A2A for agents, OpenAPI for REST.**

10. **Data Cloud / Knowledge Vault / Service Knowledge Graph / Agent OS corpus — every platform has a grounding layer** and every platform's grounding layer is the thing that determines hallucination rates. Hybrid search (Salesforce) is the current gold standard; opaque vector-only (HubSpot) is the common default; customer-provided corpus (Sierra, Decagon) is the most flexible but most work.

---

## Sources

### Agentforce
- https://www.salesforce.com/agentforce/what-is-a-reasoning-engine/atlas/
- https://engineering.salesforce.com/inside-the-brain-of-agentforce-revealing-the-atlas-reasoning-engine/
- https://www.infoworld.com/article/3542521/explained-how-salesforce-agentforces-atlas-reasoning-engine-works-to-power-ai-agents.html
- https://help.salesforce.com/s/articleView?id=sf.copilot_topics_actions.htm
- https://developer.salesforce.com/workshops/agentforce-workshop/agents/1-get-started
- https://www.salesforce.com/agentforce/agentforce-and-rag/
- https://engineering.salesforce.com/how-data-cloud-hybrid-search-combines-keyword-and-vector-retrieval-to-elevate-the-search-experience/
- https://developer.salesforce.com/docs/ai/agentforce/guide/agent-dx.html
- https://developer.salesforce.com/blogs/2025/04/invoke-agentforce-agents-with-apex-and-flow
- https://developer.salesforce.com/blogs/2025/05/call-third-party-apis-from-an-agent-with-external-service-actions
- https://developer.salesforce.com/blogs/2025/07/best-practices-for-building-agentforce-apex-actions
- https://docs.mulesoft.com/agentforce-connector/latest/
- https://developer.salesforce.com/docs/ai/agentforce/guide/agent-script.html
- https://github.com/trailheadapps/agent-script-recipes
- https://developer.salesforce.com/docs/ai/agentforce-partner/guide/agentforce-voice-sip-signaling-config.html
- https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
- https://www.sweep.io/blog/the-5-salesforce-errors-that-break-agentforce
- https://www.salesforceben.com/navigating-the-challenges-of-salesforce-flow-a-response-to-pablo-gonzalez/
- https://www.salesforceben.com/are-agentforce-hallucinations-a-problem-or-is-it-just-your-bad-data/
- https://www.getgenerative.ai/salesforce-agentforce-limitations/

### HubSpot Breeze
- https://knowledge.hubspot.com/ai/understand-breeze
- https://knowledge.hubspot.com/ai/use-assistants-and-agents-in-breeze-studio
- https://knowledge.hubspot.com/ai/use-breeze-tools
- https://knowledge.hubspot.com/customer-agent/create-a-customer-agent
- https://knowledge.hubspot.com/prospecting/use-the-prospecting-agent
- https://knowledge.hubspot.com/workflows/run-agents-using-workflows
- https://developers.hubspot.com/docs/apps/developer-platform/add-features/agent-tools/reference
- https://developers.hubspot.com/mcp
- https://knowledge.hubspot.com/integrations/customize-breeze-agents-with-hubspot-mcp-client
- https://knowledge.hubspot.com/ai-tools/get-started-using-breeze-intelligence
- https://www.hubspot.com/company-news/build-your-ai-team
- https://ecosystem.hubspot.com/marketplace/breeze-agents

### Intercom Fin
- https://fin.ai/customers/anthropic
- https://fin.ai/customers/lightspeed-transformation
- https://www.intercom.com/help/en/articles/9569407-fin-actions-explained-beta
- https://www.intercom.com/help/en/articles/8205718-fin-ai-agent-outcomes

### Zendesk
- https://www.zendesk.com/blog/zip2-relate-2025-resolution-platform-ai-agents/
- https://support.zendesk.com/hc/en-us/articles/8357756604186
- https://www.zendesk.com/service/ai/ai-agents/

### ServiceNow + Moveworks
- https://www.servicenow.com/products/ai-agents.html
- https://www.servicenow.com/blogs/2025/meet-your-new-servicenow-ai-agents
- https://www.servicenow.com/platform/now-assist.html
- https://www.moveworks.com/us/en/resources/blog/ai-agents-for-itsm-automation
- https://www.moveworks.com/us/en/platform/integrations/workday

### Microsoft Copilot Studio
- https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/explore-agents-pre-built-for-you-in-microsoft-copilot-studio/
- https://adoption.microsoft.com/en-us/ai-agents/templates-and-examples/
- https://learn.microsoft.com/en-us/microsoft-copilot-studio/

### Sierra
- https://sequoiacap.com/podcast/training-data-clay-bavor/
- https://sierra.ai/blog/theres-an-agent-for-that-and-it-runs-on-sierra
- https://sierra.ai/about
- https://sierra.ai/customers

### Decagon
- https://decagon.ai/case-studies/rippling
- https://decagon.ai/case-studies/substack
- https://decagon.ai/case-studies

### Glean
- https://www.glean.com/blog/glean-agents-launch-blog
- https://docs.glean.com/agents/how-agents-work

### Harvey
- https://www.harvey.ai/blog/paul-weiss-harvey-workflow-builder
- https://www.harvey.ai/blog/harvey-co-builds-custom-model-for-tax-with-pwc
- https://www.aoshearman.com/en/expertise/markets-innovation-group/contractmatrix
- https://www.aoshearman.com/en/news/ao-shearman-and-harvey-to-roll-out-agentic-ai-agents-targeting-complex-legal-workflows

### Ironclad / Spellbook
- https://ironcladapp.com/resources/articles/ai-agentic-launch
- https://support.ironcladapp.com/hc/en-us/articles/28661084734999
- https://www.spellbook.legal/features/review

### Devin / Cursor
- https://cognition.ai/blog/devin-annual-performance-review-2025
- https://cognition.ai/blog/how-cognition-uses-devin-to-build-devin
- https://docs.devin.ai/release-notes/overview
- https://cursor.com/blog/2-0
- https://cursor.com/docs/agent/overview
