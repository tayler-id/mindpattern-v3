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


def _stderr_snippet(stderr: str, limit: int = 300) -> str:
    return (stderr or "").strip().replace("\n", " ")[:limit]


def _summarize_failures(failures: list[dict]) -> str:
    if not failures:
        return ""
    first = failures[0]
    channel = first.get("channel", "")
    exit_code = first.get("exit_code")
    stderr = first.get("stderr", "")
    if exit_code is None:
        return f"yt-dlp {stderr} for {channel}".strip()
    return f"yt-dlp exit {exit_code} for {channel}: {stderr}".strip()


def fetch_with_diagnostics(
    channels: dict[str, str] | None = None,
    max_per_channel: int = 3,
) -> tuple[list[dict], dict]:
    channels = channels or DEFAULT_CHANNELS
    all_items = []
    failures = []

    for name, url in channels.items():
        cmd = [
            "yt-dlp", "--dump-json", "--flat-playlist",
            "--playlist-items", f"1:{max_per_channel}",
            url,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                snippet = _stderr_snippet(proc.stderr)
                logger.warning(f"yt-dlp failed for {name}: {snippet[:200]}")
                failures.append({
                    "backend": "yt-dlp",
                    "channel": name,
                    "exit_code": proc.returncode,
                    "stderr": snippet,
                })
                continue

            for line in proc.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    video = json.loads(line)
                    all_items.append(_transform(video, channel=name))
                except json.JSONDecodeError:
                    failures.append({
                        "backend": "yt-dlp",
                        "channel": name,
                        "exit_code": 0,
                        "stderr": "invalid JSON line",
                    })
                    continue

        except subprocess.TimeoutExpired:
            logger.warning(f"yt-dlp timed out for {name}")
            failures.append({
                "backend": "yt-dlp",
                "channel": name,
                "exit_code": None,
                "stderr": "timed out after 30s",
            })
        except FileNotFoundError:
            logger.error("yt-dlp not found — install with: pip install yt-dlp")
            return [], {
                "status": "unavailable",
                "reason": "yt-dlp not found",
                "channels": list(channels.keys()),
                "failures": [{
                    "backend": "yt-dlp",
                    "channel": name,
                    "exit_code": None,
                    "stderr": "yt-dlp not found",
                }],
            }
        except Exception as e:
            logger.error(f"yt-dlp failed for {name}: {e}")
            failures.append({
                "backend": "yt-dlp",
                "channel": name,
                "exit_code": None,
                "stderr": str(e)[:300],
            })

    if all_items and failures:
        status = "partial"
        reason = _summarize_failures(failures)
    elif all_items:
        status = "ok"
        reason = ""
    elif failures:
        timeout_count = sum(1 for failure in failures if "timed out" in failure.get("stderr", ""))
        status = "timeout" if timeout_count == len(failures) else "failed"
        reason = _summarize_failures(failures)
    else:
        status = "empty"
        reason = f"no YouTube items for channels: {', '.join(channels)}"

    return all_items, {
        "status": status,
        "reason": reason,
        "channels": list(channels.keys()),
        "failures": failures,
    }


def fetch(channels: dict[str, str] | None = None, max_per_channel: int = 3) -> list[dict]:
    items, _diagnostics = fetch_with_diagnostics(
        channels=channels,
        max_per_channel=max_per_channel,
    )
    return items
