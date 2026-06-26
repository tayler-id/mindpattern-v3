"""Channel → handler registry for the MindPattern Slack bot.

Channel IDs are loaded from macOS Keychain or environment variables.
Adding a new handler = create a handler file + add it to HANDLER_CLASSES.
"""

import json
import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

# Handler classes registered here. Import is deferred to avoid circular deps.
HANDLER_CLASSES: dict[str, str] = {
    "posts": "slack_bot.handlers.posts.PostsHandler",
    "skills": "slack_bot.handlers.skills.SkillsHandler",
    "tips": "slack_bot.handlers.tips.TipsHandler",
    "engagement": "slack_bot.handlers.engagement.EngagementHandler",
    "approvals": "slack_bot.handlers.approvals.ApprovalsHandler",
    "briefing": "slack_bot.handlers.briefing.BriefingHandler",
    "harness": "slack_bot.handlers.harness.HarnessHandler",
}

CHANNEL_ENV_VARS = {
    "posts": "MP_SLACK_CHANNEL_POSTS",
    "skills": "MP_SLACK_CHANNEL_SKILLS",
    "tips": "MP_SLACK_CHANNEL_TIPS",
    "engagement": "MP_SLACK_CHANNEL_ENGAGEMENT",
    "approvals": "MP_SLACK_CHANNEL_APPROVALS",
    "briefing": "MP_SLACK_CHANNEL_BRIEFING",
    "harness": "MP_SLACK_CHANNEL_HARNESS",
}

LAST_BUILD_REPORT: dict[str, object] = {}


def _keychain_get(service: str) -> str | None:
    """Read a value from macOS Keychain, falling back to the env var derived
    from the service name (slack-bot-token → SLACK_BOT_TOKEN).

    On non-macOS hosts (the Fly.io container) Keychain is skipped entirely
    and only the env var is consulted.
    """
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", service, "-a", "mindpattern", "-w"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.error(f"Keychain lookup timed out for {service}")
        except Exception as e:
            logger.error(f"Keychain lookup failed for {service}: {e}")
    return os.environ.get(service.upper().replace("-", "_")) or None


def load_channel_config() -> dict[str, str]:
    """Load channel ID mapping from Keychain or environment.

    Expects a JSON blob stored as 'slack-channel-config' in Keychain:
    {"posts": "C_POSTS_ID", "engagement": "C_ENGAGE_ID", ...}

    Falls back to environment variables:
    MP_SLACK_CHANNEL_POSTS, MP_SLACK_CHANNEL_ENGAGEMENT, etc.
    """
    import os

    # Try Keychain first
    config_json = _keychain_get("slack-channel-config")
    if config_json:
        try:
            return json.loads(config_json)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in slack-channel-config keychain entry")

    # Fallback to environment variables
    config = {}
    for name, env_var in CHANNEL_ENV_VARS.items():
        val = os.environ.get(env_var)
        if val:
            config[name] = val

    return config


def _credential_source(service: str) -> str:
    """Return where a Slack secret would be read from without exposing it."""
    env_var = service.upper().replace("-", "_")
    if os.environ.get(env_var):
        return "environment"
    if sys.platform == "darwin":
        return "keychain"
    return "missing"


def _blank_report(owner_user_id: str | None = None) -> dict[str, object]:
    return {
        "expected_names": list(HANDLER_CLASSES),
        "configured_names": [],
        "registered_names": [],
        "missing_names": list(HANDLER_CLASSES),
        "failed_names": [],
        "configured_count": 0,
        "registered_count": 0,
        "owner_configured": bool(owner_user_id),
    }


def _redacted_copy(report: dict[str, object]) -> dict[str, object]:
    """Copy only safe report fields; never include IDs, tokens, or values."""
    return {
        "expected_names": list(report.get("expected_names", [])),
        "configured_names": list(report.get("configured_names", [])),
        "registered_names": list(report.get("registered_names", [])),
        "missing_names": list(report.get("missing_names", [])),
        "failed_names": list(report.get("failed_names", [])),
        "configured_count": int(report.get("configured_count", 0)),
        "registered_count": int(report.get("registered_count", 0)),
        "owner_configured": bool(report.get("owner_configured", False)),
    }


def get_bot_doctor_report(owner_user_id: str | None = None) -> dict[str, object]:
    """Return redacted bot wiring/credential health for Slack doctor output."""
    if LAST_BUILD_REPORT:
        report = _redacted_copy(LAST_BUILD_REPORT)
    else:
        channel_config = load_channel_config()
        report = _blank_report(owner_user_id)
        configured = [
            name for name in HANDLER_CLASSES
            if channel_config.get(name)
        ]
        report["configured_names"] = configured
        report["missing_names"] = [
            name for name in HANDLER_CLASSES
            if name not in configured
        ]
        report["configured_count"] = len(configured)

    if owner_user_id is not None:
        report["owner_configured"] = bool(owner_user_id)

    report["token_sources"] = {
        "bot_token": _credential_source("slack-bot-token"),
        "app_token": _credential_source("slack-app-token"),
    }
    return report


def build_handlers(client, owner_user_id: str) -> dict[str, object]:
    """Instantiate all handlers with their channel IDs.

    Returns: {channel_id: handler_instance}
    """
    import importlib

    global LAST_BUILD_REPORT

    channel_config = load_channel_config()
    handlers = {}
    report = _blank_report(owner_user_id)
    report["missing_names"] = []

    for name, class_path in HANDLER_CLASSES.items():
        channel_id = channel_config.get(name)
        if not channel_id:
            report["missing_names"].append(name)
            logger.warning(f"No channel ID configured for '{name}' — skipping handler")
            continue

        report["configured_names"].append(name)

        # Import the handler class
        module_path, class_name = class_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            handler_class = getattr(module, class_name)
            handlers[channel_id] = handler_class(
                client=client,
                channel_id=channel_id,
                owner_user_id=owner_user_id,
            )
            report["registered_names"].append(name)
            logger.info(f"Registered {class_name} for channel {channel_id} (#{name})")
        except Exception as e:
            report["failed_names"].append(name)
            logger.error(f"Failed to load handler {class_path}: {e}")

    report["configured_count"] = len(report["configured_names"])
    report["registered_count"] = len(report["registered_names"])
    LAST_BUILD_REPORT = report

    return handlers
