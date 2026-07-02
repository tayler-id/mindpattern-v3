# Goal prompt: Rabbit Hole site writing harness quality upgrade

Paste everything from the `/goal` line into a fresh implementation session in
this worktree or another clean worktree of `mindpattern-v3`.

---

/goal Upgrade the Rabbit Hole site writer harness so AI-assisted copy reads
like credible, source-grounded, human web writing and fails closed when it
smells synthetic, generic, promotional, or unsupported.

Context:
- Current harness: `orchestrator/site_writer.py`,
  `orchestrator/site_critic.py`, `orchestrator/site_backfill.py`, and
  `orchestrator/site_content_engine.py`.
- Current rules: `docs/specs/site-writer-rules.md`,
  `agents/site-story-writer.md`, and `agents/site-story-critic.md`.
- Research input:
  `docs/research/2026-07-02-ai-writing-tells-and-human-web-copy.md`.
- The goal is not to prove authorship or add an AI detector. The goal is a
  deterministic editorial quality floor plus a stronger critic prompt.

Hard constraints:
- Do not run live writer or critic provider calls in tests.
- Do not run the newsletter pipeline (`run.py`).
- Do not touch generated `reports/` artifacts, `data/`, or social drafts.
- Preserve backfill resumability and claim behavior.
- Keep the implementation provider-neutral: Claude, Codex, and `cmd:` writers
  must all pass through the same lint and artifact gates.

Implementation loop:

1. Read the current harness and tests:
   - `orchestrator/site_writer.py`
   - `orchestrator/site_critic.py`
   - `orchestrator/site_content_engine.py`
   - `orchestrator/site_content.py`
   - `tests/test_site_writer.py`
   - `tests/test_site_critic.py`
   - `tests/test_backfill_claims.py`
   - `tests/test_backfill_cli.py`
2. Add a shared deterministic copy-lint module, likely
   `orchestrator/site_copy_lint.py`.
   - It should return structured issues with `code`, `severity`, `field`,
     `excerpt`, and `message`.
   - It must cover hard-fail issues from the research doc: banned words,
     hard-fail phrases, em dashes, invented URLs, raw markdown in public
     fields, internal machinery mentions, unsupported temporal claims, missing
     fields, and max field lengths.
   - It should cover revise-level issues: overlong sentences, body word count,
     repeated paragraph openers, generic take, echo dek, missing contraction,
     promotional adjective pile, vague attribution, summary closer, and
     uniform sentence rhythm.
3. Integrate the linter at every ingress point:
   - `parse_writer_output` rejects hard-fail lint.
   - `write_story_with_review` sends revise-level lint to the critic as
     structured evidence.
   - revised output is linted again before acceptance.
   - `evaluate_site_story_confidence` rejects hard-fail lint for final
     artifacts.
4. Update prompts:
   - Writer prompt should demand event-first lede, concrete stakes, one
     falsifiable take, source-bound uncertainty, no wrap-up, and useful
     human roughness.
   - Critic prompt should explicitly score robotic smoothness, generic advice,
     echo deks, unsupported recency, summary-of-source copy, and copy that
     could fit any competitor blog after noun swaps.
5. Add tests:
   - Unit tests for every lint code.
   - Writer parser tests proving hard-fail lint rejects agent output.
   - Critic harness tests proving revise-level lint appears in the critic
     prompt and revisions are linted again.
   - Artifact confidence tests proving final site stories cannot publish with
     hard-fail lint.
   - Backfill tests proving failed lint returns a retryable writer/gate
     outcome without touching unrelated claims.
6. Add a small fixture corpus:
   - `tests/fixtures/site_copy_lint/good/*.json`
   - `tests/fixtures/site_copy_lint/bad/*.json`
   Each bad fixture should isolate one failure reason.
7. Run focused verification:
   - `.venv/bin/python -m pytest tests/test_site_writer.py tests/test_site_critic.py tests/test_backfill_claims.py tests/test_backfill_cli.py -q`
   - Add and run the new lint/artifact tests.
   - Run `git diff --check`.
8. Final report:
   - Summarize files changed.
   - List lint codes added.
   - List tests run and results.
   - State any residual risk, especially any rules left to the critic rather
     than deterministic lint.

Definition of done:
- There is one shared deterministic copy-lint layer used by writer parsing,
  critic review, and final artifact confidence gating.
- Known AI-writing tells from the research doc are either hard-fail lint,
  revise-level lint, or intentionally documented as critic-only.
- The writer and critic prompts align with the lint layer and web-writing
  research.
- Tests prove bad synthetic copy fails closed and good sharp copy still passes.
- No live provider calls are needed for CI.
