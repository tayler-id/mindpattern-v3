#!/usr/bin/env python3
"""Blind side-by-side of two versions of the same issue, for judging a model or prompt change.

    .venv/bin/python3 tools/bakeoff.py --a /tmp/mp-replays/day-opus5/newsletter.md \\
        --b /tmp/mp-replays/day-opus55/newsletter.md --out /tmp/bakeoff/2026-09-30
    open /tmp/bakeoff/2026-09-30/compare.html      # read both, pick one
    .venv/bin/python3 tools/bakeoff.py --reveal /tmp/bakeoff/2026-09-30

The page shows "Version 1" and "Version 2" in a random order with each one's
writing-policy violation count, and never the source paths. The order is kept
in answer-key.json until --reveal.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import random
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blind bakeoff</title>
<style>
:root {{ --bg: #fafaf9; --fg: #1c1917; --muted: #57534e; --line: #d6d3d1; --surface: #ffffff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #1c1917; --fg: #e7e5e4; --muted: #a8a29e; --line: #44403c; --surface: #292524; }} }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.6 Georgia, serif; }}
header {{ padding: 16px; border-bottom: 1px solid var(--line); font-family: system-ui, sans-serif; }}
main {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px; }}
section {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 16px; min-width: 0; }}
h2 {{ font-family: system-ui, sans-serif; font-size: 14px; letter-spacing: .06em; text-transform: uppercase; margin: 0 0 4px; }}
.meta {{ font-family: system-ui, sans-serif; color: var(--muted); font-size: 13px; margin-bottom: 12px; }}
pre {{ white-space: pre-wrap; word-wrap: break-word; font: inherit; margin: 0; }}
@media (max-width: 800px) {{ main {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<header><strong>Blind bakeoff.</strong> Read both, decide which you would send, then run
<code>tools/bakeoff.py --reveal {out}</code>.</header>
<main>{columns}</main></body></html>
"""


def _column(label: str, text: str) -> str:
    from orchestrator import word_bank

    violations = word_bank.violations(text, "newsletter")
    return (f"<section><h2>{label}</h2><div class=\"meta\">{len(text.split()):,} words, "
            f"{len(violations)} writing-policy violations</div><pre>{html.escape(text)}</pre></section>")


def build(a: Path, b: Path, out: Path, *, rng: random.Random | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    pair = [("a", a), ("b", b)]
    (rng or random.Random()).shuffle(pair)
    columns = "".join(_column(f"Version {index}", path.read_text()) for index, (_, path) in enumerate(pair, 1))
    (out / "compare.html").write_text(PAGE.format(out=html.escape(str(out)), columns=columns))
    key = {f"Version {index}": {"side": side, "path": str(path)} for index, (side, path) in enumerate(pair, 1)}
    (out / "answer-key.json").write_text(json.dumps(key, indent=2))
    return key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--a", type=Path)
    parser.add_argument("--b", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--reveal", type=Path, help="print which version was which")
    args = parser.parse_args(argv)
    if args.reveal:
        for label, entry in json.loads((args.reveal / "answer-key.json").read_text()).items():
            print(f"{label}: {entry['side'].upper()} = {entry['path']}")
        return 0
    if not (args.a and args.b and args.out):
        parser.error("--a, --b and --out are required unless --reveal is given")
    build(args.a, args.b, args.out)
    print(f"open {args.out / 'compare.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
