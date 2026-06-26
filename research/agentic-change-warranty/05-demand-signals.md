# 05 — Demand Signals

Two demand forces converge: (a) AI-generated code is **measurably and persistently
defective**, and (b) incumbent insurers are **carving AI risk out** of existing policies.
Together they open a coverage gap exactly where this product sits.

---

## Signal 1 — AI code is defective at a structural rate [CONFIRMED 3-0 on the headline]

**Veracode 2025 GenAI Code Security Report** (80+ coding tasks, 100+ LLMs, production-grade
SAST): **45% of AI-generated code samples introduced OWASP Top-10 vulnerabilities.**
Corroborated by BusinessWire, Help Net Security, SD Times.

**Spring 2026 follow-up:** the finding **holds for newer/larger models** — GPT-5.1/5.2,
Gemini 3, Claude 4.5/4.6 — with pass rates clustered **~55%, essentially flat over two
years.** Independently echoed by CSA Labs and arXiv academic studies.

**Why it matters:** the problem is **structural**, not a transient artifact of immature
models. "Wait for better models" is **not** a mitigation. The risk that a warranty would
price does not evaporate. [The "won't self-resolve / strengthens warranty demand" framing
verified **2-1** — one verifier flagged it as a business inference the source doesn't make.]

**Caveat (important).** 45% is a **controlled benchmark**, not a measured **field defect
rate** of real production PRs. The leap from "AI code is buggy" to "enterprises will buy
per-PR liability transfer" is an **unproven business inference** — see file 10, open
question #1.

**Sources.**
- https://www.veracode.com/resources/analyst-reports/2025-genai-code-security-report/ *(primary)*
- https://www.veracode.com/blog/spring-2026-genai-code-security *(primary)*

---

## Signal 2 — Insurers are RETREATING from AI risk [CONFIRMED 3-0]

This is the counterintuitive, high-value signal. Incumbents pulling back **creates** the
gap rather than closing it.

**ISO / Verisk CGL exclusions, effective Jan 1 2026:**
- **CG 40 47** — generative-AI exclusion
- **CG 40 48** — generative-AI exclusion (variant)
- **CG 35 08** — AI-related exclusion
Confirmed via Verisk (IndependentAgent.com), Gallagher/AJG, Business Insurance.

**Berkley "absolute" AI exclusions (Form PC 51380)** in D&O / E&O / fiduciary policies —
barring claims "based upon, arising out of, or attributable to" any **use, deployment, or
development of AI.** Corroborated by Hunton Andrews Kurth and the National Law Review.

**Cyber insurers** are either **excluding AI losses** from existing policies or **pricing
AI separately** (Geneva Association Oct 2025 report; Fenwick LLP; ISO/Verisk endorsements).

**The kicker:** these exclusions are drafted so **broadly** they could **eliminate coverage
for AI-native companies' core operations** — leaving buyers exposed precisely where
AI-code risk lives. That exposed buyer is the **target customer** for an Agentic Change
Warranty.

**Sources.**
- https://ebuildersecurity.com/cyber-news/ai-risk-cyber-insurance-agentic-coverage-2025/ *(secondary)*
- https://www.policyholderpulse.com/ai-exclusions-insurance-policies/ *(secondary)*

---

## Signal 3 — Vendor IP indemnities exist (and may compete) [context]

Major AI vendors already offer **IP indemnification** for their coding assistants —
**GitHub Copilot**, plus **Microsoft / Google / Amazon** IP indemnity programs. Microsoft's
Copilot Copyright Commitment is documented.

**Two-edged.** (a) It proves vendors already feel pressure to **transfer some AI-output
risk** to the buyer's comfort — validating appetite. (b) It is a **potential competitor /
crowding-out force**: if Copilot already indemnifies IP claims, a warranty product must
cover the risks indemnities **don't** — i.e. **security defects, production incidents, data
leakage, license violations from the *change itself*** — not IP/copyright.

**This interaction was NOT fully resolved by the research** — see file 10, open question #1.

**Sources.**
- https://www.legaldive.com/news/microsoft-copilot-user-copyright-legal-indemnification-ip-law/693163/ *(secondary)*
- https://ipenewsletter.substack.com/p/the-ai-coding-boom-is-turning-into *(secondary)*

---

## Demand synthesis

| Force | Direction | Effect on the product |
|-------|-----------|------------------------|
| 45% AI-code defect rate, flat over 2 yrs | Structural, persistent | Creates a real, non-vanishing risk to price |
| ISO CG 40 47/48, CG 35 08 (Jan 2026) | Insurers excluding AI from CGL | Opens an unmet coverage gap |
| Berkley "absolute" AI exclusions (D&O/E&O) | Insurers excluding AI from mgmt liability | Buyers left exposed = demand |
| Cyber insurers repricing/excluding AI | Retreat | Reinforces the gap |
| Vendor IP indemnities (Copilot et al.) | Partial risk transfer already exists | Validates appetite **and** bounds scope (cover non-IP risks) |

**Bottom line:** demand pressure is **real and durable on the supply side** (insurers
retreating, code measurably risky). The **buyer-pull** half — enterprises actively asking
to *buy* per-PR code liability transfer — is **inferred, not directly evidenced.** That is
the #1 thing to validate before building. [DERIVED]
