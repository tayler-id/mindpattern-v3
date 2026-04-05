"""Tests for dashboard findings route — column allowlist validation."""

import sqlite3
import pytest

from dashboard.routes.findings import _get_distinct_values


ALLOWED_COLUMNS = {"agent", "category", "importance", "source_name"}


class TestGetDistinctValuesAllowlist:
    """_get_distinct_values must reject column names not in the allowlist."""

    def test_allowed_column_succeeds(self):
        """Known-good column names should not raise."""
        # These may return [] if no DB, but should NOT raise ValueError.
        for col in ALLOWED_COLUMNS:
            result = _get_distinct_values(col)
            assert isinstance(result, list)

    def test_sql_injection_column_rejected(self):
        """A SQL injection payload as column name must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid column"):
            _get_distinct_values("agent; DROP TABLE findings; --")

    def test_unknown_column_rejected(self):
        """An arbitrary column name not in the allowlist must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid column"):
            _get_distinct_values("password_hash")

    def test_empty_column_rejected(self):
        """Empty string column name must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid column"):
            _get_distinct_values("")
