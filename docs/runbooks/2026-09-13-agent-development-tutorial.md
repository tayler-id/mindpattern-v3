# Interactive agent-development tutorial

The user requested an interactive, detailed tutorial on Lauren @poteto's Parts 1 and 2, her pasted clarifications, and Shopify's Helix. The deliverable is a local browser course that teaches the user to direct and assess agents through original MindPattern exercises. It does not extend the production app or claim that practice simulations run repository commands.

## Work checklist

- [x] `how` over the affected subsystem. Grounded existing verification skill and runbook; this is a standalone document application.
- [x] `architect` for parallel design exploration. Two independent sketches compared a lesson stepper and semantic long workbook. A third reader judges the tradeoffs.
- [x] Write the throughput checkpoint as four todo items.
- [x] Delegate code-writing to a subagent using your configured feature model. One owner drafted the browser files in an isolated temporary Git repository. The lead stopped the owner and confirmed all writers stopped before integration, then repaired findings and verified the final artifact.
- [x] Verify on the matching surface. The actual local-file browser course passed 49 behavior assertions plus reopening, storage-failure, narrow-layout, and print-state checks.
- [x] Rebase into small, ordered commits; stack follow-ups. Skipped: commits are outside the request.
- [x] If the design is contested, `interrogate` before shipping. Skipped: the independent design judge resolved the tradeoffs.
- [x] Run Opening a PR. Skipped: a PR is outside the request.

## Throughput checkpoint

- Blocking first steps. Read the reference material and actual toolkit; define a shared lesson schema before implementing.
- Independent workstreams. The lead authors lessons in the target repository. One implementation owner writes browser UI in an isolated temporary repository. Integrate only after that owner finishes.
- Shared mutable state. No shared writable source files. Browser exercises use invented data and their own localStorage key. Existing toolkit and personal state stay untouched.
- Smallest safe decomposition. One owner handles navigation, exercises, and persistence because they share progress state. The lead owns pedagogy, attribution, and browser verification.

## Design

The independent cross-judge scored the semantic workbook 22/25 and a JavaScript-rendered lesson registry 21/25. Selected the semantic workbook as the base, with guided focus and read-all controls from the other design. HTML owns the complete curriculum, and the controller derives navigation from lesson IDs and titles. Reading remains possible without JavaScript. Explanations live in expandable panels beside the action sequence.

Model the Domain shaped the lesson-ID-based progress record and separate quiz, completion, and lab states. Separate Before Serializing Shared State kept the UI writer's temporary repository separate from the lead's curriculum. Prove It Works required driving the actual browser page, including a failing check for the deliberately wrong simulation.

Progress is keyed by lesson ID. Lab outcomes are deterministic and clearly labeled as practice. Notes remain local with a selectable Markdown export fallback. Export includes lesson prompts, notes, quiz/completion status, the edited brief, and the prototype decision.

Source articles describe the workflow. Lessons and examples are original teaching material, not a reproduction of the articles. Source notes distinguish author statements, user-pasted replies, installed pstack behavior, and this course's adaptations.

## Verification

- `node --check docs/tutorials/agent-development/tutorial.js`: passed.
- `node --check docs/tutorials/agent-development/browser-smoke.js`: passed.
- Ran `runAgentTutorialSmoke()` from `browser-smoke.js` in a fresh isolated Chrome context at the actual local `index.html`: 49 assertions passed. Covers all 14 quizzes, navigation, completion, brief generation/editing, weak pass and meaningful failure, simulated repair, empty-check rejection, prototype match/case/empty/absent queries, read-all mode, notebook export, and storage writes. Evidence: `/private/tmp/mindpattern-tutorial-browser-proof-final.json`.
- Reopened the same file and verified note, answer feedback, edited brief, prototype selection, and selected lesson restoration. Evidence: `/private/tmp/mindpattern-tutorial-reload-proof.json`.
- Injected malformed saved JSON in the isolated test context. The app preserved it, displayed a notice, and exported new in-memory notes. Evidence: `/private/tmp/mindpattern-tutorial-storage-proof.json`.
- Denied localStorage through a browser initialization script. Reading and notebook export still worked. Evidence: `/private/tmp/mindpattern-tutorial-storage-denied-proof.json`.
- Clicked the draft-exclusion checkbox and Run checks through browser controls. Observed failure identifying the exposed draft. Tab and Enter activated the repair; the result passed and the draft disappeared.
- At a 390px viewport, all lessons fit without horizontal document overflow. The mobile menu collapses while the glossary remains available. Inspected desktop and mobile screenshots at `/private/tmp/mindpattern-tutorial-desktop.png` and `/private/tmp/mindpattern-tutorial-mobile-final.png`.
- Print events expand explanations and restore reading state afterward. Checked semantic HTML for 14 lessons, 14 quizzes, 14 notebook fields, three labs, unique IDs, and existing local assets.
- Chrome console had no errors or warnings during the final run.
- Attempting the optional local HTTP server initially hit the sandbox restriction; the escalated retry found port 8765 already occupied. No process was stopped. The complete course was verified through its supported direct-file path instead.

The lead's review corrected unreadable notebook preservation, stale results after selecting different checks, restored quiz grading, editable brief defaults, export completeness, keyboard focus after repair, print explanations, and the mobile menu. A further independent curriculum-review dispatch failed at the session thread limit. The lead reviewed the curriculum against the supplied sources and current CLI source.

Not run: full backend pytest suite, live MindPattern pipeline, live providers, publication, deployment, or a new backend verification run. No application Python files changed, so the Python-change graphify step does not apply. This course adds no production dependencies or CI gates.

Changed files for this task are this runbook and `docs/tutorials/agent-development/{index.html,styles.css,tutorial.js,browser-smoke.js,README.md}`. Earlier uncommitted verification-toolkit work was preserved. No files were deleted.
