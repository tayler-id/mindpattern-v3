# Work through the agent-development course

Open [index.html](index.html) in your browser. Keep `index.html`, `styles.css`, and `tutorial.js` together. There is no installation or build step.

Start at lesson 1. Read the action sequence, try the exercise, and use **Check my reasoning** for feedback. Open the explanation panels when you want more detail. Write a response in the notebook, then mark the lesson complete when you are ready.

The course has 14 lessons. They follow one invented story-search improvement through problem definition, investigation, verification, design alternatives, architecture, planning, review, orchestration, and maintenance. The final lesson helps you prepare a real agent conversation.

Use **Read all lessons** to browse the whole course or search its text. Printing includes every lesson. The browser saves progress and notes locally when storage is available. Keep a Markdown copy with **Export prompt notebook**, especially before switching browsers or moving the course files. Quiz results and self-marked completion are separate. Free-text notes are not automatically graded.

The three browser labs build a brief, expose a misleading verification pass, and compare search prototypes. These are practice simulations with invented data. They do not call an AI service or run repository commands. Lesson 5 provides an optional exercise using the existing MindPattern CLI in a terminal or coding-agent conversation.

To serve just this course locally, run this from the repository root:

```sh
.venv/bin/python3 -m http.server 8765 --bind 127.0.0.1 --directory docs/tutorials/agent-development
```

Visit `http://127.0.0.1:8765/`. Stop that server with Ctrl-C when finished. Browser storage for the served URL is separate from storage for a directly opened file.

If that port is occupied, choose a different unused port in the command and URL. Opening `index.html` directly needs no server.

## Sources and adaptations

The lessons cite Lauren's [Part 1](https://threadnavigator.com/thread/2094457600259842065/) and [Part 2](https://threadnavigator.com/thread/2097732320606507506/) through readable copies, the [public pstack skills](https://github.com/cursor/plugins/tree/main/pstack), the [Atlas verification example](https://github.com/poteto/verification-skill-example), and [Shopify's Helix article](https://shopify.engineering/back-to-native). Lauren's clarifications about planning, verification failures, and cloud agents came from the replies supplied in this conversation.

The exercises, prompts, sample data, and teaching sequence are original material for this course. They are not a transcript of Lauren's process or Shopify's internal implementation. Current MindPattern commands were checked against local source. The source articles and public skills can evolve; use the installed skills and current repository instructions for actual work.

The existing toolkit's implementation and recorded evidence are described in the [verification runbook](../../runbooks/2026-09-11-agent-verification-toolkit.md). The [tutorial runbook](../../runbooks/2026-09-13-agent-development-tutorial.md) records this course's verification.

## Rerun the browser checks

Use a fresh browser profile or isolated context because this check writes sample answers and notes. Open the course, paste the contents of [browser-smoke.js](browser-smoke.js) into the browser's developer console, then run `await runAgentTutorialSmoke()`. The check reports 49 passed assertions or throws at the failed behavior. It also exercises notebook download. Reopen the course to inspect the persisted sample note and quiz result.
