# social/posting.py

> Platform API posting. Bluesky + LinkedIn.

## What It Does

Posts approved content to Bluesky (AT Protocol) and LinkedIn (API). Handles image uploads, thread creation, platform-specific formatting.

## Depends On

Platform API credentials from macOS Keychain. [[data/memory-db]] (pending_posts, social_posts tables).

## Called By

[[social/pipeline]].

## Key Functions

- `compress_image(path, max_bytes)` — Compresses images for Bluesky's 950KB limit. Uses `tempfile.NamedTemporaryFile(delete=False)` for safe temp file creation. Returns original path if already small enough, otherwise a new temp path. Caller must clean up if returned path differs from input.
- `BlueskyClient._upload_blob(image_path)` — Uploads image to Bluesky. Compresses if needed, cleans up temp file in `finally` block regardless of success/failure.

## Known Issues

- Distribution gap was intermittent Runs 14-18, resolved Run 19
- LinkedIn API rate limits not handled gracefully

## Fixed Issues

- `compress_image` used deprecated `tempfile.mktemp()` (race condition). Fixed 2026-04-02: replaced with `NamedTemporaryFile(delete=False)`.
- `_upload_blob` never cleaned up compressed temp files (disk leak). Fixed 2026-04-02: added `finally` block that unlinks compressed file.

## Last Modified By Harness

2026-04-02 — ticket 2026-04-01-008: tempfile fix + cleanup.
