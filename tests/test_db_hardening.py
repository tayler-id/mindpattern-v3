"""Tests for database layer hardening — WAL, foreign keys, timeouts."""

import ast
import sqlite3
from pathlib import Path

import pytest


MEMORY_CLI_PATH = Path(__file__).parent.parent / "memory_cli.py"
DASHBOARD_DB_PATH = Path(__file__).parent.parent / "dashboard" / "memory_db.py"


class TestMemoryCliUsesProperConnection:
    """memory_cli.py must use WAL mode and foreign keys like the rest of the codebase."""

    def test_memory_cli_enables_wal_mode(self):
        """_get_db() must execute PRAGMA journal_mode=WAL."""
        source = MEMORY_CLI_PATH.read_text()
        assert "journal_mode=WAL" in source, (
            "memory_cli._get_db() must enable WAL mode"
        )

    def test_memory_cli_enables_foreign_keys(self):
        """_get_db() must execute PRAGMA foreign_keys=ON."""
        source = MEMORY_CLI_PATH.read_text()
        assert "foreign_keys=ON" in source, (
            "memory_cli._get_db() must enable foreign keys"
        )


class TestDashboardDbForeignKeys:
    """dashboard/memory_db.py must enable foreign keys."""

    def test_dashboard_enables_foreign_keys(self):
        """get_memory_db() must execute PRAGMA foreign_keys=ON."""
        source = DASHBOARD_DB_PATH.read_text()
        assert "foreign_keys=ON" in source, (
            "dashboard/memory_db.py must enable PRAGMA foreign_keys=ON"
        )


class TestConnectionTimeouts:
    """All sqlite3.connect() calls must include a timeout parameter."""

    @pytest.mark.parametrize("filepath", [
        Path(__file__).parent.parent / "memory" / "db.py",
        Path(__file__).parent.parent / "memory_cli.py",
        Path(__file__).parent.parent / "dashboard" / "memory_db.py",
    ])
    def test_connect_has_timeout(self, filepath):
        """Every sqlite3.connect() call must include a timeout kwarg."""
        source = filepath.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_connect = (
                (isinstance(func, ast.Attribute) and func.attr == "connect"
                 and isinstance(func.value, ast.Name) and func.value.id == "sqlite3")
                or (isinstance(func, ast.Attribute) and func.attr == "connect"
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "sqlite3")
            )
            if not is_connect:
                continue
            has_timeout = any(
                kw.arg == "timeout" for kw in node.keywords
            )
            assert has_timeout, (
                f"{filepath.name}: sqlite3.connect() at line {node.lineno} "
                f"missing timeout parameter"
            )
