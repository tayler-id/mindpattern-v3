# 02 — Direct Competitors (the "Insurance Camp")

These are the companies closest to the idea. The recurring finding: **all of them
underwrite AI *model outputs / performance*, never the software *code artifact*.**

---

## Armilla AI — the closest analogue

**What it is.** The world's first **Lloyd's of London Coverholder / MGA dedicated
exclusively to AI liability**. Confirmed on Lloyd's own site, not just Armilla marketing.
[CONFIRMED 3-0]

**What it underwrites.** Its taxonomy is:
- **AI Model Error Liability**
- **AI Model Output Liability**
- **AI Agent Failures** (incorrect decisions, improper tool use)

Its warranty product, **"Armilla Guaranteed,"** pays out **only when an "Armilla Verified"
algorithm fails its contractual KPIs** (e.g. accuracy, bias) — reimbursing the customer's
license fee. The trigger is **model underperformance against agreed metrics.** [CONFIRMED 3-0]

**How it's structured (this is the reusable blueprint).**
- Does **not** carry risk itself. Partners with reinsurers: **Swiss Re, Greenlight Re,
  Chaucer** (warranty side); **Chaucer / Axis Capital / Convex** (liability side).
- Coverage limits raised to **$25M by Jan 2026** as "traditional insurers retreat from
  AI risk."
- Prices risk **without years of claims data**, using "hundreds of solutions tested," with
  each policy including **"independent AI system certification informed by more than 500
  AI evaluations"** (CEO Karthik Ramakrishnan, via Reuters). [CONFIRMED 3-0]

**What it does NOT cover.** Adversarial searches across multiple verifiers for any Armilla
coverage of **pull requests, code diffs, commits, GitHub, or coding assistants returned
NOTHING.** Its flagship case study (the **MKIII** loan-decisioning model) is an
output/decision risk — a model making a bad lending call — **not a code-change risk.**
[CONFIRMED 3-0]

**Sources.**
- https://www.armilla.ai/coverage *(primary)*
- https://www.armilla.ai/resources/armilla-assurance-launches-armilla-guaranteed-tm-warranty-coverage-for-ai-products-in-partnership-with-leading-insurance-companies *(primary)*
- https://www.armilla.ai/resources/armilla-ai-raises-lloyds-backed-coverage-to-25m-as-traditional-insurers-retreat-from-ai-risk *(primary)*

> **One killed claim here:** a verifier pair rejected the over-strong wording that the
> Armilla coverage page contains *literally* "no mention of code, pull requests, software
> development, AI agents, or agentic systems" — because Armilla *does* mention AI agents
> (it covers agent *decisions*). The corrected, surviving claim is the precise one above:
> it covers agent **decisions/outputs**, not code **artifacts**. See file 10.

---

## Munich Re — `aiSure`

**What it is.** A **performance-guarantee insurance** product for AI models. In Feb 2026,
Munich Re launched a partnership with **Mosaic** providing **$15M capacity** for aiSure.

**What it underwrites.** A **parametric performance guarantee**: it triggers when a model's
**error rate exceeds a threshold** — prediction errors, hallucinations, drift. Via "aiSure
Contractual Liabilities," Munich Re can back contractual performance promises an AI vendor
makes to its customers. [CONFIRMED 3-0]

**What it does NOT cover.** Same as Armilla: the covered perils are **AI model errors**,
not code changes. Flagship case studies (fraud detection, solar, battery models) are all
**output/decision** risks. No mention of PRs, diffs, or repositories. [CONFIRMED 3-0]

**Source caveat.** The Munich Re primary page (`munichre.com/.../insure-ai.html`) returned
**HTTP 403** to fetchers. The aiSure claims therefore rest on a Munich Re executive
interview (Emerj) plus the Mosaic primary release, both corroborating the parametric
error-rate trigger. [Noted in caveats]

**Sources.**
- https://www.munichre.com/en/solutions/for-industry-clients/insure-ai.html *(primary, 403 to fetchers)*

---

## Corgi — "Tech & AI Liability"

**What it is.** A startup-insurance product. Its **AI and Algorithmic Liability Endorsement
(form CORG-TECH-0038)** is an evolution of professional-liability / Tech E&O. Launched
**May 2026.**

**Who the insured is.** The **AI vendor** is the named insured. The policy covers the
vendor's **legal defense and damages** when *its own customer* alleges the vendor's AI
model/software/algorithm failed to perform. [CONFIRMED 3-0]

**What the endorsement covers (modular).** Algorithmic bias, hallucination/defamation,
training-data misuse, data poisoning, autonomous-AI bodily injury, deepfakes, service
interruption, AI IP, regulatory defense, civil fines. It is **explicitly distinct from
"bugs in human-written code."** [CONFIRMED 3-0]

**What it does NOT cover.** Adversarial search for any **per-PR / repository / code-diff**
coverage found **zero** results across Artificial Lawyer, PR Newswire, FF News, Insurance
Journal, FinTech Global. This is **E&O for the seller of an AI product**, not per-PR
underwriting of AI-generated code inside a buyer's repo. [CONFIRMED 3-0]

**Sources.**
- https://www.artificiallawyer.com/2026/05/05/corgi-launches-ai-liability-insurance/ *(secondary)*
- https://corgi.insure/ai *(primary)*

---

## Others checked (Greenlight Re, Vouch, Coalition, CFC, Testudo)

- **Greenlight Re / Swiss Re / Chaucer / Axis / Convex / Mosaic** — appear only as
  **reinsurance capacity partners** behind Armilla / Munich Re. None offer a code-change
  product directly.
- **Testudo** — a **data-driven MGA** that announced it will **begin underwriting AI risks
  in 2026.** Worth watching as a potential fast-follower into adjacent territory. [secondary]
- **Vouch, Coalition, CFC** — surfaced in cyber/AI-endorsement context (see file 05) but
  **were not found to underwrite AI code changes.** The research did **not** exhaustively
  rule out unannounced products from these labs.

---

## Summary table

| Company | Insured party | Trigger | Covers code artifact? |
|---------|---------------|---------|:---:|
| **Armilla** | AI buyer/vendor | Model fails contractual KPIs (accuracy/bias) | **No** |
| **Munich Re aiSure** | AI vendor/buyer | Model error rate exceeds threshold (parametric) | **No** |
| **Corgi** | AI **vendor** | Customer alleges vendor's AI failed (E&O) | **No** |
| **Testudo** (2026) | TBD | "AI risks" — unspecified | Unknown |
| **Agentic Change Warranty** *(proposed)* | AI **buyer / dev team** | An AI-authored **PR/diff** causes a defined loss | **Yes — the gap** |
