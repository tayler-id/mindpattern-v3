# 06 — Feasibility & Obstacles

The idea is **possible** — there is a proven structural blueprint — but it is **hard**, and
the difficulty is concentrated in actuarial science and causation, not engineering.

---

## The proven blueprint (why it's possible) [CONFIRMED 3-0]

Armilla demonstrates every structural piece an Agentic Change Warranty needs:

| Requirement | How Armilla solved it | Reusable? |
|-------------|----------------------|:---:|
| Regulatory standing to sell coverage | Lloyd's **Coverholder / MGA** | ✅ |
| Capacity without a balance sheet | Reinsurer partners (Swiss Re, Greenlight Re, Chaucer) | ✅ |
| Pricing without claims history | **Evidence/certification** layer — "500+ AI evaluations" per policy | ✅ |
| Credible limits | **$25M by Jan 2026** | ✅ |
| A warranty instrument | "Armilla Guaranteed" (pays on KPI breach) | ✅ |

**The takeaway:** you do **not** need to be an insurer, and you do **not** need decades of
loss data. You need an **MGA structure + a reinsurer partner + a defensible evidence-based
pricing method.** That is an engineering-and-partnerships problem, which is tractable.

---

## The obstacles (why it's hard)

### 1. Actuarial data scarcity + asymmetric information [CONFIRMED 3-0]
AI risk is "genuinely difficult to underwrite due to limited loss data and asymmetric
information" (Geneva Association, **600-respondent** survey). Armilla mitigates this by
pricing on **evaluations, not claims** — but its target (model runtime error rate) is far
**more measurable and parametric** than per-PR code defects.

### 2. Causation / attribution [DERIVED from confirmed inputs]
Model-performance insurers settle on a clean parametric trigger ("error rate > X%"). A
code-change warranty must prove that **a specific AI-authored diff caused a later loss** — a
breach, outage, or data leak that may surface weeks later, downstream of many other changes.
**Attribution is the central unsolved problem.** Provenance helps establish *what* the AI
wrote, but not *that it was the proximate cause* of the loss.

### 3. Provenance ≠ safety [CONFIRMED 3-0]
GitHub's docs explicitly disclaim that attestations guarantee security. So the evidence
layer can never be "provenance = coverage." It must combine provenance with independent
risk signals — which raises the cost and complexity of underwriting each PR.

### 4. Adverse selection [DERIVED]
The PRs whose authors most want coverage are disproportionately the **risky** ones. Without
strong risk-based pricing and mandatory checks, the pool skews bad. Mitigation: make
coverage **conditional on required checks** (the "insurable up to $X *if* merged after
these two checks" mechanic) so the act of buying coverage forces risk reduction.

### 5. Correlated / systemic risk [DERIVED]
Unlike independent car crashes, **one bad model release or one poisoned dependency can
break thousands of repos simultaneously.** A single Claude/GPT regression, or a compromised
popular package, is a **catastrophe-correlated** event. This is the risk most likely to
blow up a naive book — and the reason a **reinsurer/cat-cover partner is mandatory**, not
optional.

### 6. Regulatory / licensing friction [DERIVED]
Selling **insurance** requires licensing in every jurisdiction. A **warranty / guarantee**
(a direct contractual promise to pay, structured as a service rather than insurance) can
sidestep some of this — which is why a **warranty-first MVP** is the pragmatic path,
converting to a carrier-backed insurance product later (Armilla's own progression).

---

## Has anyone tried and failed?

The research found **no documented failed attempt at per-PR code-change underwriting** —
consistent with the space being genuinely unoccupied rather than tried-and-abandoned. It
also did **not** exhaustively rule out **stealth or pre-launch entrants** (Lloyd's Lab
cohorts, Vouch, Coalition, CFC, Greenlight Re, Testudo). Treat "no failures found" as "no
public activity found," not proof of impossibility.

---

## Realistic MVP — the recommended shape

1. **Instrument first, insure later.** Ship the **evidence + scoring** product (a GitHub
   App) with **no financial promise** — pure risk intelligence. Get adoption, gather the
   loss/outcome data you lack.
2. **Narrow the first warranted class.** Offer warranty only on **low-blast-radius,
   high-attribution** PRs (e.g., changes confined to a single service with strong test
   coverage and clear ownership) where causation is tractable. Resist the $1M
   regulated/security tier until calibrated.
3. **Warranty, not insurance, on day one.** A contractual guarantee with a capped,
   self-funded (or thinly reinsured) pool avoids licensing drag.
4. **Partner for capacity + cat cover.** Mirror Armilla: MGA/Coverholder + reinsurer
   (mandatory for the correlated-risk tail).
5. **Price on evidence, calibrate continuously.** Start with expert-rules pricing keyed to
   SLSA level + diff-risk + test delta + blast-radius; replace priors with measured loss
   experience as it accrues.

---

## Feasibility verdict

| Dimension | Assessment |
|-----------|------------|
| Technical (build the evidence/scoring engine) | **Feasible** — all primitives exist |
| Structural (MGA + reinsurer) | **Proven** — Armilla is the template |
| Actuarial (price per-PR risk) | **Hard, unproven** — the real frontier |
| Attribution (prove an AI diff caused a loss) | **Hardest single problem** |
| Regulatory (warranty-first) | **Manageable** via warranty instrument |
| Catastrophe/systemic risk | **Dangerous** — requires reinsurance, not optional |

**Net:** build the **evidence/scoring layer now** (low risk, real value, no licensing); gate
the **financial warranty** behind narrow scope + a reinsurer partner + accumulated loss data.
