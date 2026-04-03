# social/posting.py

> Platform API posting. Bluesky + LinkedIn.

## What It Does

Posts approved content to Bluesky (AT Protocol) and LinkedIn (API). Handles image uploads, thread creation, platform-specific formatting.

## Depends On

Platform API credentials from macOS Keychain. [[data/memory-db]] (pending_posts, social_posts tables).

## Called By

[[social/pipeline]].

## Known Issues

- Distribution gap was intermittent Runs 14-18, resolved Run 19
- LinkedIn API rate limits not handled gracefully

## Last Modified By Harness

Never — created 2026-04-01.
