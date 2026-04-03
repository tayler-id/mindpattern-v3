#!/usr/bin/env python3
"""gif-gen.py -- Render Remotion compositions to GIF.

Usage:
  python3 tools/gif-gen.py --composition-file path/to/comp.tsx --width 1080 --height 1080 --fps 15 --duration 4 --output path/to/output.gif
  python3 tools/gif-gen.py --composition-id KineticTypography --width 720 --height 720 --fps 12 --duration 4 --output path/to/output.gif

Exit codes: 0=success, 2=total failure.
Outputs JSON to stdout on success: {"success": true, "path": "...", "size_bytes": N}
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


TOOL_NAME = "gif-gen"
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
REMOTION_DIR = PROJECT_ROOT / "remotion"
COMPOSITIONS_DIR = REMOTION_DIR / "src" / "compositions"

# Max file sizes per platform (bytes)
MAX_SIZES = {
    "bluesky": 1_000_000,   # 1MB
    "linkedin": 5_000_000,  # 5MB
    "default": 5_000_000,
}

# Degradation steps for oversized GIFs
DEGRADE_STEPS = [
    {"colors": 128, "lossy": 80},
    {"colors": 64, "lossy": 120},
    {"colors": 32, "lossy": 200},
]


def _log_error(message: str, context: Optional[str] = None) -> None:
    """Print structured JSON error to stderr."""
    err = {"error": message, "tool": TOOL_NAME}
    if context:
        err["context"] = context
    print(json.dumps(err), file=sys.stderr)


def _kill_process_tree(pid: int) -> None:
    """Kill entire process tree starting from pid.

    Uses os.killpg to kill the process group, which catches child
    processes like headless Chrome spawned by Puppeteer.
    """
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    # Give processes a moment to terminate
    time.sleep(0.5)
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _validate_composition(tsx_path: Path) -> list[str]:
    """Validate a composition file for security and correctness.

    Returns list of error strings. Empty list = valid.
    """
    errors = []

    if not tsx_path.exists():
        return [f"File not found: {tsx_path}"]

    content = tsx_path.read_text()

    # Security: block dangerous Node.js built-in modules
    blocked_imports = [
        "fs", "child_process", "net", "http", "https", "os", "path",
        "crypto", "dgram", "dns", "cluster", "worker_threads",
    ]
    for module in blocked_imports:
        # Check for import statements and require calls
        if f'from "{module}"' in content or f"from '{module}'" in content:
            errors.append(f"Blocked import: {module}")
        if f'require("{module}")' in content or f"require('{module}')" in content:
            errors.append(f"Blocked require: {module}")

    # Check for allowed imports only
    import re
    imports = re.findall(r'from\s+["\']([^"\']+)["\']', content)
    for imp in imports:
        if imp.startswith("."):
            continue  # relative imports OK
        if imp.startswith("@remotion/"):
            continue
        if imp in ("react", "react-dom", "remotion"):
            continue
        errors.append(f"Unallowed import: {imp}")

    return errors


def _optimize_gif(gif_path: Path, max_size: int) -> bool:
    """Optimize GIF with gifsicle, degrading quality if needed.

    Returns True if the file is under max_size after optimization.
    """
    gifsicle = _find_gifsicle()
    if not gifsicle:
        _log_error("gifsicle not found, skipping optimization")
        return gif_path.stat().st_size <= max_size

    for step in DEGRADE_STEPS:
        if gif_path.stat().st_size <= max_size:
            return True

        cmd = [
            gifsicle,
            "--optimize=3",
            f"--colors={step['colors']}",
            f"--lossy={step['lossy']}",
            "--batch",
            str(gif_path),
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=30)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            break

    return gif_path.stat().st_size <= max_size


def _find_gifsicle() -> Optional[str]:
    """Find gifsicle binary."""
    for path in ["/opt/homebrew/bin/gifsicle", "/usr/local/bin/gifsicle"]:
        if os.path.isfile(path):
            return path
    # Try PATH
    try:
        result = subprocess.run(
            ["which", "gifsicle"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def render_composition(
    *,
    composition_id: str,
    composition_file: Optional[str] = None,
    width: int = 1080,
    height: int = 1080,
    fps: int = 15,
    duration: int = 4,
    output: str,
    platform: str = "default",
    timeout: int = 180,
) -> dict:
    """Render a Remotion composition to GIF.

    Args:
        composition_id: Remotion composition ID to render.
        composition_file: Path to a generated .tsx file (for runtime compositions).
        width: Output width in pixels.
        height: Output height in pixels.
        fps: Frames per second.
        duration: Duration in seconds.
        output: Output GIF file path.
        platform: Target platform for size limits.
        timeout: Render timeout in seconds.

    Returns:
        {"success": bool, "path": str, "size_bytes": int, "error": str|None}
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # If a composition file is provided, validate it first
    if composition_file:
        comp_path = Path(composition_file)
        errors = _validate_composition(comp_path)
        if errors:
            return {
                "success": False,
                "path": str(output_path),
                "size_bytes": 0,
                "error": f"Composition validation failed: {'; '.join(errors)}",
            }

    frames = fps * duration

    cmd = [
        "npx", "remotion", "render",
        str(REMOTION_DIR / "src" / "index.ts"),
        composition_id,
        str(output_path),
        "--codec", "gif",
        f"--width={width}",
        f"--height={height}",
        f"--every-nth-frame={max(1, round(30 / fps))}",
        f"--number-of-gif-loops=0",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(REMOTION_DIR),
            preexec_fn=os.setsid,
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _log_error(f"Render timed out after {timeout}s, killing process tree")
            _kill_process_tree(proc.pid)
            proc.wait(timeout=5)
            return {
                "success": False,
                "path": str(output_path),
                "size_bytes": 0,
                "error": f"Render timed out after {timeout}s",
            }

        if proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace")[:500]
            _log_error(f"Render failed (exit {proc.returncode})", stderr_text)
            return {
                "success": False,
                "path": str(output_path),
                "size_bytes": 0,
                "error": f"Render failed (exit {proc.returncode}): {stderr_text}",
            }

        if not output_path.exists() or output_path.stat().st_size == 0:
            return {
                "success": False,
                "path": str(output_path),
                "size_bytes": 0,
                "error": "Output file missing or empty after render",
            }

        # Optimize for target platform
        max_size = MAX_SIZES.get(platform, MAX_SIZES["default"])
        size_ok = _optimize_gif(output_path, max_size)

        size_bytes = output_path.stat().st_size
        if not size_ok:
            _log_error(
                f"GIF still exceeds {max_size} bytes after optimization: {size_bytes}",
                str(output_path),
            )

        return {
            "success": True,
            "path": str(output_path),
            "size_bytes": size_bytes,
            "optimized": size_ok,
            "platform": platform,
        }

    except FileNotFoundError:
        return {
            "success": False,
            "path": str(output_path),
            "size_bytes": 0,
            "error": "npx not found. Is Node.js installed?",
        }


def main():
    parser = argparse.ArgumentParser(description="Render Remotion composition to GIF")
    parser.add_argument("--composition-id", required=True, help="Remotion composition ID")
    parser.add_argument("--composition-file", help="Path to generated .tsx composition file")
    parser.add_argument("--width", type=int, default=1080, help="Output width")
    parser.add_argument("--height", type=int, default=1080, help="Output height")
    parser.add_argument("--fps", type=int, default=15, help="Frames per second")
    parser.add_argument("--duration", type=int, default=4, help="Duration in seconds")
    parser.add_argument("--output", required=True, help="Output GIF path")
    parser.add_argument("--platform", default="default", help="Target platform (bluesky/linkedin)")
    parser.add_argument("--timeout", type=int, default=180, help="Render timeout in seconds")
    args = parser.parse_args()

    result = render_composition(
        composition_id=args.composition_id,
        composition_file=args.composition_file,
        width=args.width,
        height=args.height,
        fps=args.fps,
        duration=args.duration,
        output=args.output,
        platform=args.platform,
        timeout=args.timeout,
    )

    print(json.dumps(result))
    sys.exit(0 if result["success"] else 2)


if __name__ == "__main__":
    main()
