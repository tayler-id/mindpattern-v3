"""Layer-manifest checker — enforces layers.toml over the import graph.

Deterministic (harness/CLAUDE.md rule: Python for everything that can be).
AST-scans every package named in the manifest and reports:

- ``undeclared-import``: a cross-package import the manifest does not
  bless (and no allowlist entry covers);
- ``container-module-level``: a container package importing an excluded
  package at module level — the class of bug local tests structurally
  cannot catch, because harness/ is always present locally and never
  present on Fly. An [[allow.deferred]] entry permits the deferred form
  only.

CLI:
    python3 -m harness.layers check [--root DIR] [--manifest FILE]
"""

from __future__ import annotations

import ast
import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_MANIFEST = PROJECT_ROOT / "layers.toml"

EXEMPT_PACKAGES = {"tests"}


@dataclass
class Violation:
    kind: str  # "undeclared-import" | "container-module-level"
    file: str
    line: int
    src: str
    dst: str
    level: str  # "module" | "deferred"

    def render(self) -> str:
        return (
            f"{self.file}:{self.line}: [{self.kind}] {self.src} imports "
            f"{self.dst} ({self.level}-level)"
        )


@dataclass
class ImportEdge:
    file: str
    line: int
    module: str
    level: str  # "module" | "deferred"


def load_manifest(path: Path | None = None) -> dict:
    manifest_path = path or DEFAULT_MANIFEST
    with open(manifest_path, "rb") as handle:
        return tomllib.load(handle)


def _scan_file(pyfile: Path, root: Path) -> list[ImportEdge]:
    """All absolute imports in one file, classified module vs deferred."""
    try:
        tree = ast.parse(pyfile.read_text())
    except (SyntaxError, OSError):
        return []

    edges: list[ImportEdge] = []
    rel = str(pyfile.relative_to(root))

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.fn_depth = 0

        def visit_FunctionDef(self, node) -> None:
            self._descend(node)

        def visit_AsyncFunctionDef(self, node) -> None:
            self._descend(node)

        def _descend(self, node) -> None:
            self.fn_depth += 1
            self.generic_visit(node)
            self.fn_depth -= 1

        def _level(self) -> str:
            return "deferred" if self.fn_depth else "module"

        def visit_Import(self, node) -> None:
            for alias in node.names:
                edges.append(ImportEdge(rel, node.lineno, alias.name, self._level()))

        def visit_ImportFrom(self, node) -> None:
            if node.module and node.level == 0:
                edges.append(ImportEdge(rel, node.lineno, node.module, self._level()))

    Visitor().visit(tree)
    return edges


def _deferred_allowed(manifest: dict, file: str, dst: str) -> bool:
    entries = manifest.get("allow", {}).get("deferred", [])
    return any(
        entry.get("file") == file and entry.get("package") == dst
        for entry in entries
    )


def check_layers(
    root: Path | None = None, manifest_path: Path | None = None
) -> dict:
    """Scan every manifest package and return {pass, violations, edges}."""
    scan_root = (root or PROJECT_ROOT).resolve()
    manifest = load_manifest(manifest_path)

    rules: dict[str, list[str]] = manifest.get("rules", {})
    container = manifest.get("container", {})
    container_packages = set(container.get("packages", []))
    excluded = set(container.get("excluded", []))
    internal = set(rules) | EXEMPT_PACKAGES

    violations: list[Violation] = []
    edge_count = 0

    for src_pkg in rules:
        pkg_dir = scan_root / src_pkg
        if not pkg_dir.is_dir():
            continue
        allowed = set(rules.get(src_pkg, []))
        for pyfile in sorted(pkg_dir.rglob("*.py")):
            for edge in _scan_file(pyfile, scan_root):
                dst = edge.module.split(".")[0]
                if dst not in internal or dst == src_pkg or dst in EXEMPT_PACKAGES:
                    continue
                edge_count += 1

                allowlisted = _deferred_allowed(manifest, edge.file, dst)

                if (
                    src_pkg in container_packages
                    and dst in excluded
                    and (edge.level == "module" or not allowlisted)
                ):
                    violations.append(Violation(
                        "container-module-level" if edge.level == "module"
                        else "undeclared-import",
                        edge.file, edge.line, src_pkg, dst, edge.level,
                    ))
                    continue

                if dst not in allowed and not allowlisted:
                    violations.append(Violation(
                        "undeclared-import",
                        edge.file, edge.line, src_pkg, dst, edge.level,
                    ))

    return {
        "pass": not violations,
        "violations": [asdict(v) for v in violations],
        "rendered": [v.render() for v in violations],
        "edges_checked": edge_count,
    }


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "check":
        print("Usage: python3 -m harness.layers check [--root DIR] [--manifest FILE]")
        return 2

    root = None
    manifest = None
    args = argv[1:]
    while args:
        flag = args.pop(0)
        if flag == "--root" and args:
            root = Path(args.pop(0))
        elif flag == "--manifest" and args:
            manifest = Path(args.pop(0))

    result = check_layers(root=root, manifest_path=manifest)
    if result["pass"]:
        print(f"layers OK: {result['edges_checked']} cross-package imports checked")
        return 0
    print(json.dumps(result["rendered"], indent=2))
    return 1


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
