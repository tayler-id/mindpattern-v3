# Build MindPattern's agent verification toolkit

## Scope

Add a project verification skill, a control CLI, and a maintained feature map for the MindPattern Python backend. Use the existing backend behavior. Preserve personal data, reports, production contracts, and operational skills. Do not add dependencies or CI gates. Commits, publishing, and production operations remain governed by the user's existing instructions.

The skills teach the coding agent what to do. The CLI lets it exercise the app. The feature map describes user behavior and the result that proves it works. Together they support requests such as "fix story search" with a repeatable demonstration of the result.

The user asked for an explanation during implementation. The lead explained these roles and clarified that MindPattern was the target assumption. No scope change followed. The requested toolkit was integrated into MindPattern, and the sandbox approved installation into `.agents/skills/` on September 13.

References read for this work:

- [Shopify's Helix and CLI approach](https://shopify.engineering/back-to-native).
- [Poteto's verification skill example](https://github.com/poteto/verification-skill-example).
- `AGENTS.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`.

## Work checklist

- [x] `how` over the affected subsystem.
- [x] `architect` for parallel design exploration.
- [x] Write the throughput checkpoint as four todo items.
- [x] Delegate code-writing to a subagent using your configured feature model.
- [x] Verify on the matching surface.
- [x] Rebase into small, ordered commits; stack follow-ups. Skipped, commits are outside this request.
- [x] If the design is contested, `interrogate` before shipping. Skipped, the design review resolved the disagreement.
- [x] Run Opening a PR. Skipped, a PR is outside this request.
- [x] Validate skill frontmatter and references, execute its documented workflow, and preserve evidence after cleanup.

## Throughput checkpoint

- Blocking first steps. Inspect startup, authentication, path selection, and existing fixtures before writing a driver.
- Independent workstreams. Explore backend isolation while the lead researches the source pattern. After agreeing on commands, write CLI code in an isolated checkout and draft skill documents separately.
- Shared mutable state. Use synthetic scratch artifacts. Never seed into `data/` or `reports/`. One implementation owner writes code. The lead integrates after that owner finishes.
- Smallest safe decomposition. One CLI implementation owner keeps startup, requests, assertions, and evidence consistent. The lead owns the skills and feature map.

## Design status

The named data shape is a feature with a stable identifier, user entry points, drive commands, observable assertions, and coverage limits. A request result records its method, path, status, body, and elapsed time.

Two design agents compared direct ASGI requests with a managed HTTP server as the default. The independent judge scored the ASGI design 24/25 and the HTTP-first design 15/25 for behavior, isolation, speed, maintainability, and evidence. Both converged on a temporary copy of current source plus synthetic artifacts. Global path patching was rejected because imported aliases and default arguments retain old roots.

Selected design: actual FastAPI app requests in a fresh isolated worker, with optional foreground Uvicorn for HTTP inspection. The CLI skips lifespan and reports that limit. It does not change production startup. Keep source hashes and revision information with responses and assertions. Exclude inherited credentials and personal state. Do not add persistent launch records or general cleanup commands.

Initial automated features: `stories`, `story-search`, `site-artifacts`, `sitemap`, and `private-access`. Broader feature-map entries will name existing tests and operational skills without claiming CLI coverage.

Implementation began in the exclusive worktree `/private/tmp/mindpattern-verification-implementation`. The lead stopped the delegate, reviewed and corrected the draft, completed tests, and integrated the files. Changes remain uncommitted. The separate worktree remains available as a draft history; the main checkout is now authoritative.

Principles used: Model the Domain selected a feature registry. Separate Before Serializing Shared State selected scratch source/data per run and an exclusive implementation worktree. Prove It Works requires running the documented CLI and retaining response/assertion evidence after cleanup.

## Verification status

Commands run from the main checkout unless a worktree path is stated:

- `.venv/bin/python3 -m pytest tests/test_verification_cli.py tests/test_auth_middleware.py tests/test_site_content_api.py -x -q`: 35 passed. An existing Starlette TestClient deprecation warning appeared. No dependency was added.
- `.venv/bin/python3 -m verification verify all --evidence /private/tmp/mindpattern-verification-final-20260913-checked`: all five scenarios passed, with 36 assertions. The evidence survived runtime cleanup. Earlier evidence directories were preserved.
- `.venv/bin/python3 -m verification doctor`: the synthetic database was connected; the synthetic bot heartbeat was stale as expected. This is not production health evidence.
- `quick_validate.py` from the installed skill-creator skill, run through `.venv/bin/python3` against each new skill: both valid.
- Local link validation: all 29 links resolved.
- `graphify update .` and `graphify check-update .`: passed. The graph HTML was skipped because the graph exceeded its visualization node limit; JSON and report outputs updated.

Real HTTP proof ran from the isolated implementation worktree using the main repository's virtual-environment interpreter. `-m verification serve --port 18011` started the synthetic app. `-m verification request '/api/stories/verification-story?user=ramsay' --base-url http://127.0.0.1:18011` returned 200 and the seeded story with its evidence. The owning terminal stopped the server. Response evidence is `/private/tmp/mindpattern-verification-http-proof.json`. The focused test suite also verifies that SIGTERM removes the server and temporary runtime.

The independent implementation review found and prompted fixes for direct internal-worker invocation, SIGTERM cleanup, and an under-specified draft fixture. A second reviewer could not start because the session reached its agent-thread limit. The lead reviewed the final changes and verified the repairs.

Not run: the full repository suite, browser rendering, application lifespan/warmup, live providers, pipeline execution, publishing, deployment, or full personal-corpus checks. The CLI's five scenarios do not claim those behaviors.

Changed files: `verification/`, `tests/test_verification_cli.py`, `.agents/skills/verify-mindpattern/`, `.agents/skills/mindpattern-checkpoints/`, `.gitignore`, and this runbook. The ignore exceptions match the existing curated-skill convention. No files were deleted. Graphify also refreshed its local generated files.
