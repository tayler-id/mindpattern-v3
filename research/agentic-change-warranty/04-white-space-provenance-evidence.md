# 04 — The White Space: Provenance & Claim-Grade Evidence

This is the heart of the product. The gap between verification and insurance is filled by a
**claim-grade evidence layer** — the artifact that lets an underwriter price an AI-authored
change. The research confirms the *components* of this layer exist as standards, but that
**no one is assembling them into an underwriter-facing evidence package**, and that
**provenance alone is explicitly insufficient** to certify safety.

---

## What "claim-grade evidence" must contain

Derived from the verified findings, an insurable PR needs a bundle of:

1. **Provenance / attestation** — cryptographic proof of *what built this and how*.
2. **Diff-risk score** — complexity, touched files, criticality.
3. **Test evidence** — coverage delta, pass/fail, mutation results.
4. **Model/tool trace** — which model/agent authored it, with which tools, under what review.
5. **Blast-radius score** — how far a failure could propagate (deps, ownership, prod reach).

The first item has real standards; the rest are assembled from existing tooling. [DERIVED,
grounded in the provenance findings below]

---

## Provenance standards that exist today

### GitHub artifact attestations + SLSA Build Levels [CONFIRMED 3-0]

GitHub Actions provides **built-in artifact attestations**. Per GitHub's own docs, verbatim:

> "Artifact attestations by itself provides **SLSA v1.0 Build Level 2**."

…and reusable workflows reach **Build Level 3**. SLSA defines a **published, cumulative,
graded standard (Levels L0–L3)** — exactly the kind of ladder an underwriter can key
**coverage tiers** to.

**But — the critical caveat (this is load-bearing):** the same GitHub docs state:

> "Artifact attestations are ***not* a guarantee that an artifact is secure**… [they] link
> you to the source code and build instructions," requiring consumers to "make an informed
> risk decision."

**Implication:** provenance is **necessary but insufficient.** It can *authenticate and
tier* an AI commit; it **cannot by itself certify** it as safe to warrant. Underwriting
must fuse provenance **with** diff-risk + test evidence + blast-radius.

> **One killed claim here:** a stronger wording — that attestations create
> "cryptographically signed, **unfalsifiable** provenance and integrity **guarantees**" —
> was **refuted 0-3**, precisely because GitHub disclaims the "guarantee." Use the careful
> wording above. See file 10.

**Source.** https://docs.github.com/en/actions/concepts/security/artifact-attestations *(primary)*; https://slsa.dev/spec/v1.0/levels *(primary)*

---

### sigstore for AI agent provenance

sigstore (keyless signing, transparency log) is being discussed as a way to sign **AI
agent** actions/artifacts — extending the same provenance machinery from human builds to
agent-authored work. Establishes that the cryptographic substrate for "who/what/which
model produced this" is available off the shelf.

**Source.** https://www.alwaysfurther.ai/blog/sigstore-ai-agent-provenance *(blog)*

---

### SLSA provenance — deeper mechanics

SLSA provenance binds an artifact to the **workflow, repository, commit SHA, and triggering
event** that produced it. The graded levels (build integrity, isolation, hermeticity) give
you discrete, auditable rungs to anchor pricing tiers.

**Source.** https://www.legitsecurity.com/blog/slsa-provenance-blog-series-part-2-deeper-dive-into-slsa-provenance *(blog)*

---

## The "audit trail ≠ evidence" insight

Two sources hammer a point that is central to the product's defensibility:

> An AI agent's raw audit trail is **not, by itself, legal-grade evidence.** To be
> claim-grade it needs integrity (tamper-evidence), attribution (who/what acted),
> completeness, and admissibility.

This is the moat. **Anyone** can log what an agent did. Turning that log into something an
underwriter or a court will accept as the basis for a payout is the hard, valuable part —
and it is exactly the layer no incumbent is building.

**Sources.**
- https://dev.to/pqbuilder/your-ai-agents-audit-trail-is-not-evidence-heres-what-makes-it-one-32f7 *(blog)*
- https://truescreen.io/articles/agent-to-agent-audit-trail/ *(blog)*

---

## Cyber-insurance riders are starting to reshape underwriting around evidence

AI-specific cyber riders are emerging that **reshape underwriting and security**, signaling
insurers will increasingly demand structured security evidence as a condition of coverage —
a tailwind for a product that *produces* that evidence in a standardized, priceable form.

**Source.** https://www.aicerts.ai/news/ai-cyber-insurance-riders-reshape-underwriting-and-security/ *(blog)*

---

## Net conclusion for this angle

- The **building blocks of provenance are standardized and free** (SLSA, GitHub
  attestations, sigstore, in-toto).
- **No one has assembled them into an underwriter-facing, claim-grade evidence object for
  AI-authored code changes.** [CONFIRMED — gap]
- The defensible value is **not** the provenance primitive; it's the **assembly + scoring +
  admissibility** layer that converts provenance-plus-context into a priceable risk object.
- **Hard constraint:** because provenance ≠ safety, the product cannot be "provenance =
  coverage." It must be "provenance + diff-risk + tests + blast-radius → score → tier →
  warranty."
