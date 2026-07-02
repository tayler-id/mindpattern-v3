"""Tests for run-launchd.sh scheduling guardrails."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_launchd_skip_requires_delivery_and_sync_markers():
    """The wrapper must retry delivered-but-not-synced days."""
    source = (PROJECT_ROOT / "run-launchd.sh").read_text()

    assert 'SYNC_MARKER="${MARKER_DIR}/mindpattern-synced-${TODAY}"' in source
    assert 'if [ -f "$MARKER" ] && [ -f "$SYNC_MARKER" ]; then' in source
    assert 'Delivery marker exists but sync marker is missing' in source


def test_launchd_defaults_to_skip_social():
    """Scheduled runs should not block on social approval gates by default."""
    source = (PROJECT_ROOT / "run-launchd.sh").read_text()

    assert 'MP_LAUNCHD_SKIP_SOCIAL:-1' in source
    assert 'RUN_ARGS+=(--skip-social)' in source
    assert 'run.py "${RUN_ARGS[@]}" "$@"' in source


def test_launchd_enables_site_story_writer_by_default():
    """Nightly site stories get the live writer unless explicitly disabled."""
    source = (PROJECT_ROOT / "run-launchd.sh").read_text()

    assert 'MP_SITE_STORY_WRITER="${MP_SITE_STORY_WRITER:-claude}"' in source
