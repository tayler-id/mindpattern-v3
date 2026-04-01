#!/usr/bin/env python3
"""image-gen.py — Generate images via Flux 2 Pro (BFL) or OpenAI GPT Image 1.5.

Usage:
  python3 tools/image-gen.py --prompt "..." --width 1080 --height 1350 --output path/to/image.png
  python3 tools/image-gen.py --prompt "..." --width 1200 --height 628 --output path/to/image.png
  python3 tools/image-gen.py --prompt "..." --engine openai --width 1024 --height 1536 --output path/to/image.png

Exit codes: 0=success, 2=total failure.
"""

import argparse
import base64
import json
import struct
import subprocess
import sys
import time
import urllib.request
import urllib.error
import zlib
from typing import Optional


TOOL_NAME = "image-gen"
RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_DELAYS = [1, 2, 4]


def _log_error(message: str, context: Optional[str] = None) -> None:
    """Print structured JSON error to stderr."""
    err = {"error": message, "tool": TOOL_NAME}
    if context:
        err["context"] = context
    print(json.dumps(err), file=sys.stderr)


def _fetch_with_retry(
    url: str,
    headers: Optional[dict] = None,
    timeout: int = 30,
    data: Optional[bytes] = None,
    method: Optional[str] = None,
) -> bytes:
    """Fetch URL with retry + exponential backoff for transient HTTP errors.

    Returns the response body as bytes.
    Raises on non-retryable errors or after exhausting retries.
    """
    if headers is None:
        headers = {}
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    last_exc: Optional[Exception] = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code in RETRYABLE_CODES and attempt < MAX_RETRIES:
                delay = BACKOFF_DELAYS[attempt]
                _log_error(
                    f"HTTP {e.code} (attempt {attempt + 1}/{MAX_RETRIES + 1}), retrying in {delay}s",
                    context=url,
                )
                time.sleep(delay)
                continue
            raise
        except (urllib.error.URLError, OSError) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                delay = BACKOFF_DELAYS[attempt]
                _log_error(
                    f"Network error (attempt {attempt + 1}/{MAX_RETRIES + 1}): {e}, retrying in {delay}s",
                    context=url,
                )
                time.sleep(delay)
                continue
            raise

    raise last_exc  # type: ignore[misc]


def get_keychain(service: str) -> str:
    """Read a secret from macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        _log_error(f"Keychain lookup timed out for '{service}'")
        sys.exit(2)
    if result.returncode != 0:
        _log_error(f"Could not read '{service}' from Keychain")
        sys.exit(2)
    return result.stdout.strip()


# -- Flux 2 Pro (BFL) ---------------------------------------------------------

def generate_flux(prompt: str, width: int, height: int, output_path: str) -> None:
    """Call Flux 2 Pro via BFL API (async polling)."""
    api_key = get_keychain("bfl-api-key")

    request_body = json.dumps({
        "prompt": prompt,
        "width": width,
        "height": height,
        "output_format": "png"
    }).encode("utf-8")

    try:
        body = _fetch_with_retry(
            "https://api.bfl.ai/v1/flux-2-pro",
            headers={
                "accept": "application/json",
                "x-key": api_key,
                "Content-Type": "application/json",
            },
            timeout=30,
            data=request_body,
            method="POST",
        )
        submit_result = json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass
        _log_error(f"Flux submit failed: HTTP {e.code}: {error_body}")
        print(json.dumps({"success": False, "error": f"HTTP {e.code}: {error_body}"}))
        sys.exit(2)
    except Exception as e:
        _log_error(f"Flux submit failed: {e}")
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(2)

    request_id = submit_result.get("id")
    polling_url = submit_result.get("polling_url", f"https://api.bfl.ai/v1/get_result?id={request_id}")

    # Poll for result
    for _ in range(120):  # max 60 seconds
        time.sleep(0.5)
        try:
            poll_body = _fetch_with_retry(
                polling_url,
                headers={
                    "accept": "application/json",
                    "x-key": api_key,
                },
                timeout=10,
            )
            result = json.loads(poll_body.decode("utf-8"))
        except Exception as e:
            _log_error(f"Flux polling error: {e}", context=polling_url)
            continue

        status = result.get("status")
        if status == "Ready":
            image_url = result["result"]["sample"]
            urllib.request.urlretrieve(image_url, output_path)
            print(json.dumps({
                "success": True,
                "engine": "flux-2-pro",
                "output": output_path,
                "width": width,
                "height": height
            }))
            return
        elif status in ("Error", "Failed", "Moderation"):
            _log_error(f"Flux generation failed with status: {status}")
            print(json.dumps({"success": False, "error": f"Flux status: {status}", "details": result}))
            sys.exit(2)

    _log_error("Flux polling timeout after 60s")
    print(json.dumps({"success": False, "error": "Polling timeout after 60s"}))
    sys.exit(2)


# -- Placeholder image (stdlib-only PNG generation) ----------------------------

def generate_placeholder(width: int, height: int, output_path: str) -> None:
    """Generate a simple dark gray placeholder PNG using only stdlib.

    Creates a minimal valid PNG with dark background (#1a1a2e).
    No PIL/Pillow dependency required.
    """
    # Build a minimal 1-pixel-row PNG and repeat for height
    # Using RGBA: dark gray-blue background
    bg_r, bg_g, bg_b = 0x1a, 0x1a, 0x2e

    def _png_chunk(chunk_type, data):
        # type: (bytes, bytes) -> bytes
        chunk = chunk_type + data
        crc = zlib.crc32(chunk) & 0xffffffff
        return struct.pack(">I", len(data)) + chunk + struct.pack(">I", crc)

    # PNG signature
    signature = b'\x89PNG\r\n\x1a\n'

    # IHDR: width, height, bit_depth=8, color_type=2 (RGB)
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _png_chunk(b'IHDR', ihdr_data)

    # Build raw image data: filter byte (0) + RGB pixels per row
    raw_row = b'\x00' + bytes([bg_r, bg_g, bg_b]) * width
    raw_data = raw_row * height

    # IDAT: compressed image data
    compressed = zlib.compress(raw_data)
    idat = _png_chunk(b'IDAT', compressed)

    # IEND
    iend = _png_chunk(b'IEND', b'')

    with open(output_path, 'wb') as f:
        f.write(signature + ihdr + idat + iend)

    print(json.dumps({
        "success": True,
        "engine": "placeholder",
        "output": output_path,
        "width": width,
        "height": height,
        "reason": "Content policy refusal or generation failure"
    }))


# -- OpenAI GPT Image 1.5 -----------------------------------------------------

def generate_openai(prompt: str, width: int, height: int, quality: str, output_path: str) -> None:
    """Call OpenAI GPT Image 1.5.

    On content policy refusal, generates a placeholder image and returns
    structured JSON instead of exiting with code 2.
    """
    api_key = get_keychain("openai-api-key")

    valid_sizes = ["1024x1024", "1024x1536", "1536x1024"]
    size = f"{width}x{height}"
    if size not in valid_sizes:
        size = "auto"

    request_body = json.dumps({
        "model": "gpt-image-1",
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": 1
    }).encode("utf-8")

    try:
        body = _fetch_with_retry(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=120,
            data=request_body,
            method="POST",
        )
        result = json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass
        # Check for content policy refusal (AC: #5)
        if e.code == 400 and "content_policy" in error_body.lower():
            _log_error(
                f"OpenAI content policy refusal: {error_body}",
                context="Generating placeholder image instead"
            )
            generate_placeholder(width, height, output_path)
            return
        _log_error(f"OpenAI image gen failed: HTTP {e.code}: {error_body}")
        print(json.dumps({"success": False, "error": f"HTTP {e.code}: {error_body}"}))
        sys.exit(2)
    except Exception as e:
        _log_error(f"OpenAI image gen failed: {e}")
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(2)

    image_data = result.get("data", [{}])[0]

    if "b64_json" in image_data:
        img_bytes = base64.b64decode(image_data["b64_json"])
        with open(output_path, "wb") as f:
            f.write(img_bytes)
    elif "url" in image_data:
        urllib.request.urlretrieve(image_data["url"], output_path)
    else:
        _log_error("No image data in OpenAI response")
        print(json.dumps({"success": False, "error": "No image data in response"}))
        sys.exit(2)

    print(json.dumps({
        "success": True,
        "engine": "openai-gpt-image-1",
        "output": output_path,
        "width": width,
        "height": height,
        "quality": quality
    }))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate images via Flux 2 Pro or GPT Image 1.5")
    parser.add_argument("--prompt", required=True, help="Image generation prompt")
    parser.add_argument("--width", type=int, default=1080, help="Image width")
    parser.add_argument("--height", type=int, default=1350, help="Image height")
    parser.add_argument("--engine", default="flux", choices=["flux", "openai"], help="Image generation engine")
    parser.add_argument("--quality", default="medium", choices=["low", "medium", "high"], help="Quality (openai only)")
    parser.add_argument("--output", default="output.png", help="Output file path")
    parser.add_argument("--placeholder", action="store_true", help="Generate a placeholder image (no API call)")
    args = parser.parse_args()

    if args.placeholder:
        generate_placeholder(args.width, args.height, args.output)
    elif args.engine == "flux":
        generate_flux(args.prompt, args.width, args.height, args.output)
    else:
        generate_openai(args.prompt, args.width, args.height, args.quality, args.output)
