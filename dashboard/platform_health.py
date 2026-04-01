"""Platform health checks — LinkedIn token expiry monitoring."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOCIAL_CONFIG_PATH = PROJECT_ROOT / "social-config.json"
LINKEDIN_REFRESH_FILE = PROJECT_ROOT / "data" / "linkedin-token-refreshed.txt"


def check_linkedin_token_health(
    refresh_file: Optional[Path] = None,
    config_path: Optional[Path] = None,
    today: Optional[datetime] = None,
) -> dict:
    """Check LinkedIn OAuth token health based on last refresh date.

    Returns {
        "healthy": bool,          # True if >7 days remaining
        "warning": bool,          # True if <=7 days remaining but not expired
        "expired": bool,          # True if 0 or fewer days remaining
        "days_remaining": int,    # Days until expiry (can be negative)
        "days_since_refresh": int,
        "expires_days": int,      # Total token lifetime from config
        "refresh_date": str,      # ISO date of last refresh
        "message": str | None,    # Human-readable warning/error message
    }
    """
    path = refresh_file or LINKEDIN_REFRESH_FILE
    cfg_path = config_path or SOCIAL_CONFIG_PATH
    now = today or datetime.now()

    # Load token lifetime from config
    expires_days = 60
    try:
        config = json.loads(cfg_path.read_text())
        expires_days = config.get("platforms", {}).get("linkedin", {}).get("token_expires_days", 60)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to parse platform health config: {e}")

    # Read last refresh date
    if not path.exists():
        return {
            "healthy": False,
            "warning": True,
            "expired": False,
            "days_remaining": -1,
            "days_since_refresh": -1,
            "expires_days": expires_days,
            "refresh_date": None,
            "message": "LinkedIn token refresh file not found. Cannot determine token health.",
        }

    try:
        refreshed_str = path.read_text().strip()
        refreshed_date = datetime.strptime(refreshed_str, "%Y-%m-%d")
    except (ValueError, OSError) as exc:
        return {
            "healthy": False,
            "warning": True,
            "expired": False,
            "days_remaining": -1,
            "days_since_refresh": -1,
            "expires_days": expires_days,
            "refresh_date": None,
            "message": f"Cannot parse LinkedIn token refresh date: {exc}",
        }

    days_since = (now - refreshed_date).days
    days_remaining = expires_days - days_since
    refresh_date_str = refreshed_date.strftime("%Y-%m-%d")

    if days_remaining <= 0:
        return {
            "healthy": False,
            "warning": False,
            "expired": True,
            "days_remaining": days_remaining,
            "days_since_refresh": days_since,
            "expires_days": expires_days,
            "refresh_date": refresh_date_str,
            "message": (
                f"LinkedIn token EXPIRED ({abs(days_remaining)} days ago). "
                f"Refreshed {days_since} days ago on {refresh_date_str}. "
                f"Refresh at: https://www.linkedin.com/developers/tools/oauth"
            ),
        }

    if days_remaining <= 7:
        return {
            "healthy": False,
            "warning": True,
            "expired": False,
            "days_remaining": days_remaining,
            "days_since_refresh": days_since,
            "expires_days": expires_days,
            "refresh_date": refresh_date_str,
            "message": (
                f"LinkedIn token expires in {days_remaining} day{'s' if days_remaining != 1 else ''}. "
                f"Refreshed {days_since} days ago on {refresh_date_str}. "
                f"Refresh at: https://www.linkedin.com/developers/tools/oauth"
            ),
        }

    return {
        "healthy": True,
        "warning": False,
        "expired": False,
        "days_remaining": days_remaining,
        "days_since_refresh": days_since,
        "expires_days": expires_days,
        "refresh_date": refresh_date_str,
        "message": None,
    }
