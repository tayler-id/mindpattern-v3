# 10 — Caveats, Open Questions & Refuted Claims

Read this file before acting on anything. It records what the research is **not** sure of,
the claims that **failed** verification, and the questions that remain **open**.

---

## Caveats (from the synthesis)

### Time-sensitivity
A fast-moving market; findings anchor to the **late-2025 / mid-2026** window:
- Armilla expanded limits to **$25M** (Jan 2026)
- Munich Re × Mosaic launched aiSure partnership, **$15M** capacity (Feb 2026)
- Corgi launched (May 2026)
- ISO / Berkley exclusions took effect (Jan 2026)
- Testudo announced AI underwriting for 2026

**→ A new entrant could close this gap quickly.**

### Source quality
Incumbent findings lean on **vendor marketing pages**, partly mitigated by independent
corroboration. **Munich Re primary URL = HTTP 403** to fetchers; aiSure rests on an exec
interview (Emerj) + Mosaic release. Corgi/cyber/ISO/Berkley findings are **secondary**
sources backed by primary filings (form numbers) and AmLaw commentary.

### Interpretive inferences (treat as hypotheses, not facts)
- The Veracode **45%** figure is a **controlled benchmark**, not a measured **field defect
  rate** of real production PRs.
- The leap from "AI code is buggy" → "enterprises will buy per-PR liability transfer" is an
  **unproven business inference**. Actual procurement/legal **buyer-pull** demand was **not
  directly evidenced.**
- "Underwriters could key coverage tiers to SLSA" is framed **conditionally** — **no insurer
  is documented doing this today.**

### Feasibility nuance
The hardest obstacle (limited loss data + asymmetric information) is **confirmed**. Armilla's
"price via evaluations not claims data" is a **self-reported** methodology, **not
independently actuarially audited** — and it prices **model performance** (a measurable,
parametric target) rather than **per-PR code defects** (harder to attribute causation for).

---

## Refuted / killed claims (2 of 25) — do NOT repeat these

### KILLED — vote 1-2
> "The Armilla coverage page contains **no mention** of code, pull requests, software
> development, AI agents, or agentic systems."

**Why it failed:** too strong. Armilla **does** reference AI agents (it covers agent
*decisions / improper tool use*). The **surviving, corrected** claim: Armilla covers AI
agent **decisions/outputs**, **not** code **artifacts/PRs**. Use the corrected version
(file 02).

### KILLED — vote 0-3
> "GitHub Actions artifact attestations create cryptographically signed, **unfalsifiable**
> provenance and integrity **guarantees**."

**Why it failed:** GitHub's own docs **explicitly disclaim** that attestations guarantee
security ("*not* a guarantee that an artifact is secure"). Overstating this would poison the
product thesis. The **correct** framing: attestations provide graded SLSA provenance
(authenticate what/how) but are **necessary-but-insufficient** for safety (file 04).

---

## Open questions (the four things to resolve before building)

### 1. Is there documented buyer-pull demand for code-change liability transfer?
The **defect-rate** and **insurer-retreat** data are strong, but **no source directly
evidenced buyers asking for or paying for per-PR code warranties** — nor how AI-vendor IP
indemnities (Copilot, Microsoft/Google/Amazon) **interact with or crowd out** such a
product. **This is the #1 validation target.**

### 2. Can per-PR code risk actually be priced parametrically?
Armilla/Munich Re settle on measurable runtime accuracy thresholds. A code-change warranty
must solve **causation/attribution** (prove an AI diff caused a later breach), **adverse
selection** (worst PRs seek coverage), and **correlated/systemic risk** (one bad model
update poisons many repos at once). **None were resolved by the evidence.**

### 3. What's the right instrument and trigger?
True insurance policy vs. MGA-bound warranty vs. non-insurance "warranty/guarantee"
(avoiding insurance licensing)? And what does the claim-grade evidence package actually
contain, given provenance alone is **insufficient**?

### 4. Are stealth/early entrants already building the evidence-to-underwriter layer?
The research confirmed **incumbents are NOT** in this space but did **not exhaustively rule
out** unannounced or pre-launch entrants (Lloyd's Lab cohorts, Vouch, Coalition, CFC,
Greenlight Re, Testudo). **"No competitor found" ≠ "no competitor exists."**

---

## Suggested next research / validation steps

1. **Customer discovery** — interview 15–20 eng/security/legal leaders at AI-heavy
   companies: would they buy per-PR liability transfer, and at what price? (resolves OQ#1)
2. **Indemnity teardown** — read the actual Copilot/Microsoft/Google/Amazon indemnity terms;
   map exactly what they do **not** cover (security defects, incidents, license-of-the-
   change). (resolves OQ#1)
3. **Attribution prototype** — can you, from telemetry, causally tie a production incident
   back to a specific AI-authored diff? Build the hardest piece first. (resolves OQ#2)
4. **Insurer conversations** — talk to Lloyd's Lab, Armilla, Testudo, a cyber MGA: would
   they consume an underwriter-pricing API for AI code? (resolves OQ#3, OQ#4)
5. **Re-run this deep-research** in ~60–90 days given market velocity. (resolves OQ#4)
