"""Channel → handler registry for the MindPattern Slack bot.

Channel IDs are loaded from macOS Keychain or environment variables.
Adding a new handler = create a handler file + add it to HANDLER_CLASSES.
"""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

# Handler classes registered here. Import is deferred to avoid circular deps.
HANDLER_CLASSES: dict[str, str] = {
    "posts": "slack_bot.handlers.posts.PostsHandler",
    "skills": "slack_bot.handlers.skills.SkillsHandler",
    "tips": "slack_bot.handlers.tips.TipsHandler",
    "engagement": "slack_bot.handlers.engagement.EngagementHandler",
    "approvals": "slack_bot.handlers.approvals.ApprovalsHandler",
    "briefing": "slack_bot.handlers.briefing.BriefingHandler",
}


def _keychain_get(service: str) -> str | None:
    """Read a value from macOS Keychain."""
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
    return None


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
    env_map = {
        "posts": "MP_SLACK_CHANNEL_POSTS",
        "skills": "MP_SLACK_CHANNEL_SKILLS",
        "tips": "MP_SLACK_CHANNEL_TIPS",
        "engagement": "MP_SLACK_CHANNEL_ENGAGEMENT",
        "approvals": "MP_SLACK_CHANNEL_APPROVALS",
        "briefing": "MP_SLACK_CHANNEL_BRIEFING",
    }
    for name, env_var in env_map.items():
        val = os.environ.get(env_var)
        if val:
            config[name] = val

    return config


def build_handlers(client, owner_user_id: str) -> dict[str, object]:
    """Instantiate all handlers with their channel IDs.

    Returns: {channel_id: handler_instance}
    """
    import importlib

    channel_config = load_channel_config()
    handlers = {}

    for name, class_path in HANDLER_CLASSES.items():
        channel_id = channel_config.get(name)
        if not channel_id:
            logger.warning(f"No channel ID configured for '{name}' — skipping handler")
            continue

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
            logger.info(f"Registered {class_name} for channel {channel_id} (#{name})")
        except Exception as e:
            logger.error(f"Failed to load handler {class_path}: {e}")

    return handlers
