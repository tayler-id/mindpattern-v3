# 07 — Opportunities

Six concrete product opportunities fall out of the gap. They are ordered from **lowest risk
/ buildable now** to **highest risk / highest ceiling**. Most teams should ship #1 → #2 →
#3 in sequence and treat #4–#6 as expansions.

> Legend: **Build risk** = engineering difficulty. **Market risk** = will anyone pay.
> **Moat** = defensibility. All grounded in the findings; the products themselves are
> [DERIVED] synthesis.

---

## Opportunity 1 — The Underwriting Evidence Layer ("turn a PR into an insurable event")

**The wedge. Build this first.** A GitHub-native product that, for every AI-authored PR,
emits a **claim-grade evidence package**: provenance attestation + diff-risk score + test
evidence + model/tool trace + blast-radius score, bundled into a signed, tamper-evident,
machine-readable object.

- **Why it exists:** verification tools (Sonar/Qodo/CodeRabbit) produce *quality* signal but
  not a *priceable risk object*; insurers (Armilla/Munich Re/Corgi) price *model outputs*
  but have no code-artifact evidence to price. This layer bridges them. (Files 03, 04)
- **No financial promise yet** — pure risk intelligence. Sidesteps all licensing.
- **Business model:** SaaS per-seat or per-repo; usage-based for the evidence API.
- **Moat:** "audit trail ≠ evidence" — assembling integrity + attribution + admissibility
  is the hard, defensible part. (File 04)

| Build risk | Market risk | Moat | Time-to-MVP |
|:--:|:--:|:--:|:--:|
| Low–Med | Medium | Medium–High | Weeks |

---

## Opportunity 2 — Underwriter-Pricing API (sell scoring to the insurers)

Expose the evidence + risk score as an **API that insurers consume** — Armilla, Munich Re,
Corgi, Testudo, and cyber carriers who want to price AI-code exposure but have no
code-artifact telemetry.

- **Why it exists:** insurers are *retreating* from AI because they "can't underwrite what
  they can't measure" (file 05). You sell them the measurement. You become the **data/risk
  rail** beneath multiple carriers rather than competing with them.
- **Business model:** API licensing / per-scored-PR / rev-share on policies enabled.
- **Strategic note:** this is the **"arms dealer"** position — lower capital, no
  underwriting risk, and you're upstream of whoever wins the insurance layer.

| Build risk | Market risk | Moat | Time-to-MVP |
|:--:|:--:|:--:|:--:|
| Low | Medium–High | Medium | Weeks–Months |

---

## Opportunity 3 — The Agentic Change Warranty (the headline product)

Attach an actual **financial warranty** to qualifying PRs: risk tier → coverage eligibility
→ certificate. The originating idea's tiers (illustrative): ~$10k internal / ~$100k
customer-facing / ~$1M+ regulated.

- **Mechanic:** *"This PR is insurable up to $250k **if** merged after these two required
  checks."* Coverage is **conditional on risk-reducing actions** — which also fights
  adverse selection (file 06).
- **Structure:** **warranty-first**, MGA/Coverholder + reinsurer for capacity and the
  catastrophe tail (Armilla's proven path, file 06).
- **Start narrow:** low-blast-radius, high-attribution PR classes only. Earn the right to
  the $1M tier with calibration data.
- **Business model:** warranty premium (% of coverage), or bundled into a higher SaaS tier.

| Build risk | Market risk | Moat | Time-to-MVP |
|:--:|:--:|:--:|:--:|
| High (partnerships + actuarial) | High | High | Quarters |

---

## Opportunity 4 — "AI Bill of Materials" / Provenance Infrastructure for AI commits

A standalone product (or open standard + hosted service) that issues **graded provenance**
for AI-authored changes: who/what model, which tools, which agent, what review — signed
with sigstore, tiered to SLSA Build Levels, exported as an attestation. (File 04)

- **Why it exists:** the provenance primitives are free but **fragmented**; nobody packages
  an "AIBOM for code changes" as a first-class, queryable, exportable artifact.
- **Adjacent demand:** AI cyber riders increasingly **demand structured security evidence**
  as a condition of coverage (file 04) — this product produces it.
- **Business model:** infra/SaaS; compliance & procurement buyers; feeds Opportunities 1–3.

| Build risk | Market risk | Moat | Time-to-MVP |
|:--:|:--:|:--:|:--:|
| Low–Med | Medium | Medium | Weeks |

---

## Opportunity 5 — Coverage-Gap / Compliance product riding the insurer retreat

A focused product for companies suddenly **excluded** by ISO CG 40 47/48, CG 35 08, or
Berkley "absolute" AI exclusions (file 05). Help them (a) **document** their AI-code risk
posture to negotiate coverage back, or (b) buy a **narrow warranty** for the carved-out
exposure.

- **Why it exists:** Jan 2026 exclusions left AI-native companies exposed in their core
  operations. That's an acute, dated, addressable pain.
- **Business model:** compliance SaaS + brokered warranty; sell through insurance brokers
  who now have a "gap" to explain to clients.

| Build risk | Market risk | Moat | Time-to-MVP |
|:--:|:--:|:--:|:--:|
| Low | Medium | Low–Med | Weeks |

---

## Opportunity 6 — Warranty-backed channel for AI vendors & consultancies

License the warranty so **coding-agent platforms, AI consultancies, and dev shops** can
sell *"our agentic work is warrantied"* into conservative enterprises — the procurement/
legal/cyber buyers who "trust indemnity more than dashboards."

- **Why it exists:** vendor IP indemnities already exist (Copilot et al., file 05),
  proving appetite — but they cover **IP only**, not security/incident/license risk of the
  *change*. This fills the non-IP half and becomes a **sales enablement** wrapper for the
  whole AI-coding ecosystem.
- **Business model:** B2B2B — white-label warranty + evidence API to platforms/consultancies.

| Build risk | Market risk | Moat | Time-to-MVP |
|:--:|:--:|:--:|:--:|
| Med–High | Medium | Med–High (distribution) | Quarters |

---

## Recommended sequencing

```
  NOW            NEXT              LATER
  ┌────────┐     ┌────────────┐    ┌──────────────────────┐
  │  #1    │ ──► │  #2  +  #4 │ ─► │  #3  →  #5 / #6       │
  │evidence│     │API + AIBOM │    │ warranty → channel    │
  │ layer  │     │            │    │ (needs reinsurer +    │
  │(no $$ ) │     │(arms       │    │  loss data)          │
  └────────┘     │ dealer)    │    └──────────────────────┘
                 └────────────┘
   build &        monetize         take underwriting risk
   get data       without risk     only once calibrated
```

**Why this order:** #1 and #4 have the lowest build/market risk and **generate the loss data
and attribution evidence** that the actuarial problem (file 06) demands. #2 monetizes
**without** taking underwriting risk. Only after the evidence flywheel turns do you take on
the warranty (#3) and its catastrophe tail — backed by a reinsurer, exactly as Armilla did.

See [`08-technology-stack.md`](08-technology-stack.md) for how to build each component.
