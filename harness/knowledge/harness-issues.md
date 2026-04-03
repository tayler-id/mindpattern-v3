# harness/issues.py + ISSUES.md

> Shared append-only issue log. Every component writes here when something breaks. All harness agents read it before acting.

## How It Works

- `ISSUES.md` is the log file (markdown, newest first)
- `issues.py` provides the Python API and CLI
- Entries have: timestamp, source, title, details
- The knowledge graph `summary()` includes ISSUES.md **first** (highest priority)

## Who Writes

| Component | When | Source field |
|-----------|------|-------------|
| Pipeline (`run-launchd.sh`) | Crash (exit != 0) | `pipeline` |
| Harness fix agent (`run.sh`) | Test failure | `harness/fix` |
| Harness review agent (`run.sh`) | PR rejected | `harness/review` |
| Humans | Manual | any |

## Who Reads

- **Fix agents** — via `--append-system-prompt` (cached across parallel agents)
- **Scout** — via knowledge summary + explicit instruction in scout.md
- **Review agents** — via knowledge summary

## CLI

```bash
python3 -m harness.issues log "source" "title" "details"
python3 -m harness.issues read [--limit N]
```

## Connected To

Read by [[harness/run]] (fix agents, scout). Included in `knowledge_graph.summary()`.

## Created

2026-04-02.
