# Agentic Change Warranty — Research Dossier

> **Question researched:** Is "AI Work Insurance for agent-generated software changes"
> (a product that underwrites, warrants, and financially guarantees AI-generated code
> changes per pull-request) viable, technically/commercially possible, and is anyone
> already building it as of **mid-2026**?

**Method:** Deep-research multi-agent harness — 5 search angles → 23 sources fetched →
105 claims extracted → 25 adversarially verified (3-vote, need 2/3 to refute) →
23 confirmed, 2 killed → synthesized into 7 high-confidence findings.

**Run stats:** 105 agents · ~2.59M tokens · 636 tool uses · ~16 min wall-clock.

---

## One-line verdict

**Genuine, defensible white space.** No company underwrites, warrants, or risk-scores
AI-authored pull requests or code diffs. Every adjacent incumbent insures **AI model
outputs/performance** (hallucinations, accuracy, bias, drift, agent decisions) against
agreed KPIs — never the **software code artifact**. AI code-review tools provide
**verification only**, with zero risk transfer. The proven, viable structure is an
**MGA/warranty layer backed by a reinsurer**, priced via an **evidence/certification
layer** rather than actuarial loss data.

---

## How to read this dossier

| File | What's in it |
|------|--------------|
| [`01-verdict-and-executive-summary.md`](01-verdict-and-executive-summary.md) | The full verdict, the reframe, the strongest wedge |
| [`02-direct-competitors.md`](02-direct-competitors.md) | Armilla, Munich Re aiSure, Corgi — exactly what each does and does **not** cover |
| [`03-adjacent-verification-tools.md`](03-adjacent-verification-tools.md) | SonarQube AI Code Assurance, Qodo, CodeRabbit — verification, no risk transfer |
| [`04-white-space-provenance-evidence.md`](04-white-space-provenance-evidence.md) | SLSA, GitHub attestations, sigstore — the necessary-but-insufficient evidence layer |
| [`05-demand-signals.md`](05-demand-signals.md) | Veracode 45%, ISO/Berkley exclusions, insurer retreat, vendor indemnity |
| [`06-feasibility-and-obstacles.md`](06-feasibility-and-obstacles.md) | Actuarial gap, adverse selection, attribution, the MGA blueprint |
| [`07-opportunities.md`](07-opportunities.md) | **Six concrete product opportunities** derived from the gap |
| [`08-technology-stack.md`](08-technology-stack.md) | **The technology to build each one** — components, tools, libraries |
| [`09-sources.md`](09-sources.md) | All 23 sources with quality ratings and the angle each served |
| [`10-caveats-open-questions-refuted.md`](10-caveats-open-questions-refuted.md) | What's uncertain, the 2 killed claims, the 4 open questions |
| [`index.html`](index.html) | Standalone visual explainer of the opportunities + tech |

---

## Confidence legend (used throughout)

- **[CONFIRMED 3-0]** — all three adversarial verifiers agreed the claim holds.
- **[CONFIRMED 2-1]** — held, but one verifier dissented (noted inline).
- **[KILLED]** — failed verification; documented in file 10 so it isn't repeated.
- **[DERIVED]** — our synthesis/inference on top of the evidence, not a sourced fact.

---

_Generated 2026-06-19 from deep-research run `wf_47c8b040-113`._
