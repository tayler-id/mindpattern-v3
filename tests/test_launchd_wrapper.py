"""Tests for run-launchd.sh scheduling guardrails."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_launchd_skip_requires_delivery_and_sync_markers():
    """The wrapper must retry delivered-but-not-synced days."""
    source = (PROJECT_ROOT / "run-launchd.sh").read_text()

    assert 'SYNC_MARKER="${MARKER_DIR}/mindpattern-synced-${TODAY}"' in source
    assert 'if [ -f "$MARKER" ] && [ -f "$SYNC_MARKER" ]; then' in source
    assert 'Delivery marker exists but sync marker is missing' in source
