# 01 — Verdict & Executive Summary

## The verdict

The **"Agentic Change Warranty"** concept — a product that turns each AI-authored pull
request into an **insurable event** (risk tier + required checks + merge recommendation +
warranty eligibility + coverage certificate) — sits in **genuine, defensible white space
as of mid-2026**. Nobody is doing it.

But the research forces one important **reframe**, which the originating agent had already
started circling:

> The product is **not** "AI insurance" — Armilla, Munich Re, and Corgi are already there.
> The product is **not** "AI code review" — Sonar, Qodo, and CodeRabbit are already there.
> The product **is** the **claim-grade underwriting evidence layer** that sits *between*
> them: the thing that turns a verified PR into something an insurer can price.

The wedge, stated precisely:

> **"We turn an AI-generated PR into an insurable event."**

## Why the gap exists (the structural picture)

The market today has two populated camps and an empty middle:

```
  VERIFICATION CAMP                 [ ── THE GAP ── ]            INSURANCE CAMP
  (no money on the line)        claim-grade evidence +         (no code coverage)
                                  risk transfer on the
  SonarQube AI Code Assurance      CODE ARTIFACT itself        Armilla  (model KPIs)
  Qodo                                                          Munich Re aiSure (error rate)
  CodeRabbit                     ← nobody is here →            Corgi    (vendor E&O)
  Greptile / Graphite / Diamond
```

- **Verification tools** tell you a PR is probably fine. They attach **no warranty,
  insurance, indemnity, or financial coverage** of any kind. [CONFIRMED 3-0]
- **AI insurers** pay out when a *model's behavior* breaches agreed KPIs (accuracy, bias,
  drift, hallucination, agent decisions). None of them touch **pull requests, diffs,
  commits, GitHub, or coding assistants** — adversarial search for any such coverage
  returned nothing. [CONFIRMED 3-0]

## The four pillars that make it credible

1. **The structure is already proven viable.** Armilla AI operates as the world's first
   Lloyd's-of-London **Coverholder/MGA dedicated to AI liability**. It does **not** carry
   risk itself — it partners with reinsurers (Swiss Re, Greenlight Re, Chaucer), with
   limits raised to **$25M by Jan 2026**. Crucially, it prices AI risk via an
   **evidence/certification layer** ("more than 500 AI evaluations" per policy), **not**
   traditional actuarial loss data. That is the exact blueprint an Agentic Change Warranty
   would follow. [CONFIRMED 3-0]

2. **Demand pressure is structural, not a fad.** Veracode's 2025 GenAI Code Security
   Report found AI-generated code introduced OWASP Top-10 vulnerabilities in **45%** of
   test cases — and a Spring 2026 follow-up confirmed **newer/larger models did not
   improve** (pass rates flat ~55% across GPT-5.x, Gemini 3, Claude 4.5/4.6). The defect
   problem will **not** self-resolve as models get better. [CONFIRMED 3-0 on 45%;
   2-1 on "won't self-resolve"]

3. **Incumbent insurers are retreating, which *widens* the gap.** ISO added three optional
   generative-AI exclusions to commercial general liability (CG 40 47, CG 40 48, CG 35 08,
   effective **Jan 1 2026**); Berkley introduced **"absolute" AI exclusions** in D&O/E&O
   (Form PC 51380). Cyber insurers are excluding or separately repricing AI losses. The
   buyer's AI-code exposure is being carved *out* of existing policies — leaving an open
   coverage gap precisely where this product would sit. [CONFIRMED 3-0]

4. **A gradable provenance standard already exists** to anchor coverage tiers. GitHub
   artifact attestations satisfy **SLSA v1.0 Build Level 2** out of the box (Level 3 via
   isolated reusable workflows). An underwriter could key coverage tiers to provenance
   level. [CONFIRMED 3-0]

## The dominant risk

The single hardest obstacle is **actuarial + attribution**:

- Limited loss data and asymmetric information make AI risk "genuinely difficult to
  underwrite" (Geneva Association, 600-respondent survey). [CONFIRMED 3-0]
- **Provenance alone is explicitly *not* a guarantee** that a change is secure — GitHub's
  own docs say so. So the evidence layer is *necessary but insufficient*; underwriting must
  fuse provenance **with** diff-risk, test evidence, and blast-radius scoring. [CONFIRMED 3-0]
- Model-performance insurers settle on a **measurable runtime error rate** — a clean
  parametric trigger. A code-change warranty must instead solve **causation/attribution**
  (proving an AI diff caused a later breach), **adverse selection** (the worst PRs seek
  coverage), and **correlated/systemic risk** (one bad model update poisons many repos at
  once). None of these are solved by the evidence gathered. [DERIVED from confirmed inputs]

## The realistic MVP shape

**MGA / warranty-first, backed by a carrier — not standalone "true" insurance.**

1. Build the **claim-grade evidence package** (provenance attestation + diff-risk score +
   test evidence + model/tool trace + blast-radius) as a GitHub-native product.
2. Expose it as an **underwriter-pricing API**.
3. Start with a **warranty/guarantee** instrument (a contractual promise to pay, possibly
   non-insurance, to avoid licensing friction) over a **narrow, low-blast-radius PR class**
   where attribution is tractable.
4. Partner with a reinsurer/MGA platform for capacity once loss experience accrues —
   mirroring Armilla's path.

See [`07-opportunities.md`](07-opportunities.md) for the six concrete products and
[`08-technology-stack.md`](08-technology-stack.md) for how to build them.

## Time-sensitivity warning

This is a fast-moving market. Armilla hit $25M limits (Jan 2026); Munich Re × Mosaic
launched an aiSure partnership ($15M capacity, Feb 2026); Corgi launched (May 2026); a
data-driven MGA called **Testudo** announced it would begin underwriting AI risks in 2026;
ISO/Berkley exclusions took effect Jan 2026. **A new entrant could close this gap quickly.**
The research confirmed incumbents are *not* in this space but did **not** exhaustively rule
out unannounced/pre-launch startups or insurer innovation labs (Lloyd's Lab, Vouch,
Coalition, CFC, Greenlight Re).
