# 03 — Adjacent Verification Tools (the "Verification Camp")

These tools verify AI-generated code. **None of them attaches any financial warranty,
insurance, indemnification, or risk transfer.** They define the *lower* boundary of the gap:
they produce signal but never put money on the line.

---

## SonarQube — "AI Code Assurance"

**What it is.** Sonar's positioning around AI code — "Fight AI Slop & Verify AI Code,"
"Agentic Analysis" to verify AI code as agents write it, SonarQube as "the trust and
verification layer for your AI code."

**What "AI Code Assurance" actually offers.** Exactly **three mechanisms**:
1. **Project labeling** (tag a project as containing AI-generated code)
2. **Enforced quality gate** (block merge unless quality thresholds pass)
3. **Badge publishing** (display an "assured" badge)

**What it does NOT offer.** **Zero** mentions of warranty, guarantee, insurance,
indemnification, or financial coverage in marketing or official docs. Searches combining
"AI Code Assurance" with warranty/insurance/indemnification surfaced **no risk-transfer
language whatsoever.** [CONFIRMED 3-0]

This is the cleanest single confirmation of the gap: the market leader in "AI code
assurance" assures **quality**, not **liability**.

**Sources.**
- https://www.sonarsource.com/solutions/ai/ai-code-assurance/ *(primary)*
- https://docs.sonarsource.com *(primary)*

---

## Qodo

**What it is.** An AI code-review and governance platform — context-aware review, bug
detection, rules, standards, compliance, agentic quality workflows.

**Risk transfer?** None found. Strong adjacent competitor on the *verification* axis; **no
public risk-transfer or warranty language.** [from angle research]

**Source.** https://www.qodo.ai/blog/best-ai-code-review-tools-2026/ *(blog)*

---

## CodeRabbit

**What it is.** AI-powered PR/IDE/CLI review — pulls codebase intelligence, MCP context,
linters, scanners; markets to "AI-powered teams who move fast," tells teams to "do the
final 10%."

**Risk transfer?** None. Verification layer, not insurance layer. [from angle research]

**Source.** https://www.coderabbit.ai/blog/coderabbit-tops-martian-code-review-benchmark *(blog)*

---

## Others in the camp (named, same conclusion)

**Graphite, Greptile, Diamond** — AI code-review / PR-automation tools. All occupy the
verification axis; none was found attaching warranty or risk transfer.

---

## Why this matters for the wedge

The verification camp is **a feeder, not a competitor.** Their output (quality-gate pass,
static-analysis findings, review verdict) is exactly the kind of **evidence** an
underwriting layer consumes. A smart strategy treats Sonar/Qodo/CodeRabbit signals as
**inputs** to the claim-grade evidence package rather than trying to out-review them.

```
  Verification tools  ──►  evidence  ──►  [ Agentic Change Warranty ]  ──►  underwriter
  (Sonar/Qodo/CR)          package          risk score + certificate        prices it
```

> **Strategic read:** Do **not** try to build a better code reviewer. Build the layer that
> converts *any* reviewer's output — plus provenance, tests, and blast-radius — into a
> priceable risk object. That's the defensible position between the two crowded camps.
