"""Tests for harness/layers.py — the layer-manifest checker."""

from pathlib import Path

import pytest

from harness.layers import check_layers

MANIFEST = """
[container]
packages = ["webapp"]
excluded = ["outer"]

[rules]
core = []
webapp = ["core"]
outer = ["core"]

[[allow.deferred]]
file = "webapp/handlers/outer_cmd.py"
package = "outer"
reason = "deliberate deferred import with fallback"
"""


@pytest.fixture
def fake_tree(tmp_path):
    """A miniature repo with core, webapp (container), and outer (Mac-only)."""
    manifest = tmp_path / "layers.toml"
    manifest.write_text(MANIFEST)
    for pkg in ("core", "webapp", "outer", "webapp/handlers"):
        (tmp_path / pkg).mkdir(parents=True, exist_ok=True)
        (tmp_path / pkg / "__init__.py").write_text("")
    return tmp_path, manifest


def _check(tree):
    root, manifest = tree
    return check_layers(root=root, manifest_path=manifest)


class TestRules:
    def test_blessed_import_passes(self, fake_tree):
        root, _ = fake_tree
        (root / "webapp" / "app.py").write_text("from core import db\n")
        result = _check(fake_tree)
        assert result["pass"], result["rendered"]

    def test_undeclared_import_flagged(self, fake_tree):
        root, _ = fake_tree
        (root / "core" / "util.py").write_text("import webapp\n")
        result = _check(fake_tree)
        assert not result["pass"]
        assert result["violations"][0]["kind"] == "undeclared-import"
        assert result["violations"][0]["src"] == "core"
        assert result["violations"][0]["dst"] == "webapp"

    def test_stdlib_and_external_imports_ignored(self, fake_tree):
        root, _ = fake_tree
        (root / "core" / "util.py").write_text("import json\nimport requests\n")
        result = _check(fake_tree)
        assert result["pass"]

    def test_intra_package_imports_ignored(self, fake_tree):
        root, _ = fake_tree
        (root / "core" / "a.py").write_text("from core import b\n")
        result = _check(fake_tree)
        assert result["pass"]


class TestContainerRule:
    """The invariant local tests cannot catch: locally the excluded package
    is always importable, on Fly it does not exist."""

    def test_module_level_excluded_import_flagged(self, fake_tree):
        root, _ = fake_tree
        (root / "webapp" / "app.py").write_text("from outer import tickets\n")
        result = _check(fake_tree)
        assert not result["pass"]
        assert result["violations"][0]["kind"] == "container-module-level"

    def test_allowlisted_deferred_import_passes(self, fake_tree):
        root, _ = fake_tree
        (root / "webapp" / "handlers" / "outer_cmd.py").write_text(
            "def cmd():\n    from outer import tickets\n    return tickets\n"
        )
        result = _check(fake_tree)
        assert result["pass"], result["rendered"]

    def test_allowlisted_file_module_level_still_flagged(self, fake_tree):
        root, _ = fake_tree
        (root / "webapp" / "handlers" / "outer_cmd.py").write_text(
            "from outer import tickets\n"
        )
        result = _check(fake_tree)
        assert not result["pass"]
        assert result["violations"][0]["kind"] == "container-module-level"

    def test_deferred_but_not_allowlisted_flagged(self, fake_tree):
        root, _ = fake_tree
        (root / "webapp" / "app.py").write_text(
            "def cmd():\n    from outer import tickets\n"
        )
        result = _check(fake_tree)
        assert not result["pass"]

    def test_syntax_error_file_skipped_not_fatal(self, fake_tree):
        root, _ = fake_tree
        (root / "webapp" / "broken.py").write_text("def (\n")
        result = _check(fake_tree)
        assert result["pass"]


class TestRealRepo:
    def test_current_tree_satisfies_manifest(self):
        """The ratchet: the shipped layers.toml must stay green on the
        shipped tree. A new cross-package import either gets declared
        here deliberately or gets removed."""
        result = check_layers()
        assert result["pass"], "\n".join(result["rendered"])
        assert result["edges_checked"] > 50
