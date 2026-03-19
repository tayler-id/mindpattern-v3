"""Preflight: YouTube videos from key AI channels via yt-dlp."""

import json
import logging
import subprocess

from . import make_entry

logger = logging.getLogger(__name__)

DEFAULT_CHANNELS = {
    "AI Explained": "https://www.youtube.com/@aiexplained-official/videos",
    "Fireship": "https://www.youtube.com/@Fireship/videos",
    "Matthew Berman": "https://www.youtube.com/@matthew_berman/videos",
    "Yannic Kilcher": "https://www.youtube.com/@YannicKilcher/videos",
    "Dwarkesh Patel": "https://www.youtube.com/@DwarkeshPatel/videos",
}


def _transform(raw: dict, channel: str = "") -> dict:
    url = raw.get("webpage_url") or raw.get("url", "")
    return make_entry(
        source="youtube",
        source_name=channel or raw.get("channel", "YouTube"),
        title=raw.get("title", ""),
        url=url,
        published="",
        content_preview=(raw.get("description", "") or "")[:500],
        metrics={"views": raw.get("view_count", 0) or 0},
    )


def fetch(channels: dict[str, str] | None = None, max_per_channel: int = 3) -> list[dict]:
    channels = channels or DEFAULT_CHANNELS
    all_items = []

    for name, url in channels.items():
        cmd = [
            "yt-dlp", "--dump-json", "--flat-playlist",
            "--playlist-items", f"1:{max_per_channel}",
            url,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                logger.warning(f"yt-dlp failed for {name}: {proc.stderr[:200]}")
                continue

            for line in proc.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    video = json.loads(line)
                    all_items.append(_transform(video, channel=name))
                except json.JSONDecodeError:
                    continue

        except subprocess.TimeoutExpired:
            logger.warning(f"yt-dlp timed out for {name}")
        except FileNotFoundError:
            logger.error("yt-dlp not found — install with: pip install yt-dlp")
            return []
        except Exception as e:
            logger.error(f"yt-dlp failed for {name}: {e}")

    return all_items
