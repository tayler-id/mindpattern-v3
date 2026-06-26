# 08 — Technology Stack: How To Build It

This maps each component of the evidence → scoring → warranty pipeline to concrete,
buildable technology. Everything here uses **existing, mostly open-source primitives** —
the value is in **assembly + scoring + admissibility**, not inventing new cryptography.

> Architecture in one line:
> **GitHub event → collect signals → score risk → assemble signed evidence → (optionally)
> price + issue warranty certificate → expose via API.**

---

## System architecture

```
        GitHub PR (tagged ai-generated)
                  │  webhook
                  ▼
        ┌─────────────────────┐
        │   Ingest / GitHub    │  Probot / Octokit · Checks API · webhooks
        │        App           │
        └─────────┬───────────┘
                  ▼
   ┌──────────────────────────────────────── Signal Collectors (parallel) ──┐
   │ Diff-risk  │ Security/  │ Deps &    │ Provenance/ │ Model/tool │ Blast  │
   │ (AST)      │ secrets    │ license   │ attestation │ trace      │ radius │
   └─────┬──────┴─────┬──────┴─────┬─────┴──────┬──────┴─────┬──────┴───┬────┘
         └────────────┴────────────┴────────────┴────────────┴──────────┘
                                   ▼
                    ┌──────────────────────────┐
                    │   Risk Scoring Engine     │  rules → calibrated ML
                    │   (tier + required checks)│
                    └─────────────┬────────────┘
                                  ▼
                    ┌──────────────────────────┐
                    │  Claim-grade Evidence      │  in-toto + sigstore +
                    │  Package (signed, append-  │  SLSA attestation, hashed
                    │  only, tamper-evident)     │  to a transparency log
                    └─────────────┬────────────┘
                          ┌───────┴────────┐
                          ▼                ▼
              ┌────────────────┐   ┌────────────────────┐
              │ Underwriter    │   │ Warranty / Cert     │
              │ Pricing API    │   │ issuance + policy DB │
              └────────────────┘   └────────────────────┘
```

---

## Layer 1 — Ingest (the GitHub-native surface)

| Need | Technology |
|------|-----------|
| Receive PR events | **GitHub App** via **Probot** (Node) or **octokit** (any lang); webhooks for `pull_request`, `check_run` |
| Post status / gate merges | **GitHub Checks API**, **commit statuses**, **branch protection** required checks |
| Tag AI-authored work | PR labels (`ai-generated`), **commit trailers** (`Co-Authored-By:`, `Generated-By:`), Git notes |
| Inline findings | Checks API annotations / review comments |
| Run compute | **GitHub Actions** (reusable workflows — also gets you SLSA L3, see Layer 5) or a hosted worker |

**Languages:** TypeScript/Node for the App surface; Python or Go for collectors and scoring.

---

## Layer 2 — Diff-risk collector

| Signal | Technology |
|--------|-----------|
| Parse the diff into structured AST | **tree-sitter** (multi-language), `git diff --numstat`, **difftastic** for structural diffs |
| Complexity | cyclomatic/cognitive complexity (**lizard**, **radon** for Py, **gocyclo**), churn metrics |
| File criticality | **CODEOWNERS** weighting, historical incident map, path heuristics (auth/, payments/, migrations/) |
| Test-coverage delta | parse **lcov** / `coverage.py` / `gocov`; map changed lines → covered lines |
| Mutation / test strength | **Stryker**, **mutmut**, **PIT** (optional, premium signal) |

---

## Layer 3 — Security & secrets collector

| Signal | Technology |
|--------|-----------|
| SAST on the diff | **Semgrep** (rules + OSS), **CodeQL**, optionally **Snyk Code** / **Veracode** APIs |
| Secret exposure | **gitleaks**, **trufflehog**, GitHub secret scanning |
| Diff-scoped findings | Semgrep `--baseline`, CodeQL diff-informed queries |
| OWASP mapping | tag findings to OWASP Top-10 (mirrors the Veracode benchmark, file 05) |

---

## Layer 4 — Dependencies & license collector

| Signal | Technology |
|--------|-----------|
| Generate SBOM | **Syft** → **CycloneDX** / **SPDX** |
| Vulnerable deps | **Grype**, **OSV-Scanner** (OSV.dev), **Dependabot** alerts API |
| License changes/conflicts | **ScanCode Toolkit**, **FOSSA**/**licensee**; flag GPL-into-proprietary, etc. |
| New-dependency risk | diff the SBOM across the PR; weight newly-introduced transitive deps |

---

## Layer 5 — Provenance & attestation (the load-bearing layer)

This is what makes the evidence **claim-grade**. (File 04)

| Need | Technology |
|------|-----------|
| Build provenance | **SLSA** provenance; **GitHub artifact attestations** (→ SLSA Build L2 OOTB, **L3** via isolated reusable workflows) |
| Signing (keyless) | **sigstore / cosign**, Fulcio (certs), **Rekor** (transparency log) |
| Attestation format | **in-toto** attestations, **DSSE** envelopes |
| Tamper-evidence | append-only Merkle log (Rekor or **Trillian**); hash-chain the evidence bundle |
| ⚠️ Hard constraint | Provenance authenticates *what/how*, **not** *that it's safe* — GitHub disclaims this. Always **combine** with Layers 2–4. (File 04, 06) |

---

## Layer 6 — Model / tool / agent trace

| Signal | Technology |
|--------|-----------|
| Which model/agent authored | commit trailers, PR metadata, IDE/agent plugin telemetry |
| Tool-call / agent run trace | **OpenTelemetry GenAI semantic conventions**, **OpenLLMetry**, structured agent logs |
| Human-review quality | reviewer count, time-to-review, review depth, who approved (Checks/Reviews API) |
| Make the trace evidence-grade | sign + hash into the attestation (Layer 5); "audit trail ≠ evidence" → enforce integrity + attribution + completeness (File 04) |

---

## Layer 7 — Blast-radius scoring

| Signal | Technology |
|--------|-----------|
| Code dependency graph | **tree-sitter** call graphs, **Sourcegraph SCIP/LSIF**, language servers |
| Ownership / reach | CODEOWNERS, service catalog (**Backstage**), monorepo graph (**Nx**/**Bazel** query) |
| Production reach | feature-flag exposure (LaunchDarkly), deploy targets, traffic/criticality from APM (Datadog/OTel) |
| Output | a 0–1 "how far can a failure propagate" score → drives the coverage **tier** |

---

## Layer 8 — Risk scoring engine

| Stage | Technology |
|-------|-----------|
| v0 — expert rules | weighted rules over Layers 2–7; transparent, auditable, no data needed |
| Tiering | map score → {internal / customer-facing / regulated} → coverage cap + **required checks** |
| v1 — calibrated model | gradient-boosted trees (**XGBoost/LightGBM**) once labeled outcomes accrue; **calibration** (Platt/isotonic) is essential for pricing |
| Explainability | **SHAP** values per PR — needed for both buyer trust and underwriter audit |
| Feedback loop | record merge→incident outcomes; retrain priors → measured loss experience (File 06) |

---

## Layer 9 — Evidence package (the deliverable object)

| Property | Technology |
|----------|-----------|
| Schema | JSON-LD / CycloneDX-style; embed scores, findings, provenance, trace, tier |
| Integrity | DSSE-signed, hash-chained, anchored in Rekor/Trillian |
| Admissibility | timestamps (RFC 3161 TSA), signer identity (Fulcio), completeness manifest |
| Distribution | OCI registry attachment (cosign attach), or content-addressed store (S3 + hash) |

---

## Layer 10 — Underwriting / warranty backend

| Need | Technology |
|------|-----------|
| Pricing API | REST/GraphQL; input = evidence package, output = tier + premium + eligibility |
| Policy / certificate store | **PostgreSQL** (event-sourced); certificate PDFs (signed) |
| Carrier/reinsurer integration | partner APIs (MGA/Coverholder), bordereaux reporting; structured as **warranty-first** (File 06) |
| Actuarial/pricing | start parametric + expert priors; evolve to loss-experience pricing; reinsurance/cat-cover for systemic risk (File 06) |
| Compliance | warranty instrument (avoid insurance licensing at MVP), audit logs, SOC 2 path |

---

## Build stack summary (opinionated default)

- **App surface:** TypeScript + Probot/Octokit on GitHub Apps + Actions
- **Collectors:** Python/Go services; Semgrep, gitleaks, Syft/Grype/OSV, tree-sitter, lizard
- **Provenance:** sigstore (cosign/Fulcio/Rekor), in-toto, SLSA via GitHub attestations
- **Trace:** OpenTelemetry GenAI conventions / OpenLLMetry
- **Scoring:** rules → XGBoost + SHAP, calibrated
- **Data:** PostgreSQL (event-sourced), OCI registry / S3 for evidence blobs
- **API:** FastAPI or Node; signed JSON evidence + pricing endpoint
- **Insurance:** MGA/Coverholder + reinsurer partner; warranty-first instrument

**Nothing here requires inventing new technology.** The defensibility is the **assembly,
the scoring calibration, the admissibility of the evidence, and the underwriting
partnerships** — exactly the layers no incumbent is building. (Files 02–04)
