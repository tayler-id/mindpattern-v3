#!/usr/bin/env python3
"""Verify LinkedIn access token and API connectivity WITHOUT posting.

Usage:
    python3 tools/linkedin-verify.py

Reads the access token from macOS Keychain (linkedin-access-token) and
calls the LinkedIn /v2/userinfo endpoint to confirm the token is valid.
Reports the person URN, name, and token status.

Does NOT create any posts or modify any LinkedIn data.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from social.posting import LinkedInClient, keychain_get


def main():
    print("=" * 60)
    print("LinkedIn Token & API Verification")
    print("=" * 60)
    print()

    # Step 1: Load config
    config_path = PROJECT_ROOT / "social-config.json"
    try:
        with open(config_path) as f:
            config = json.load(f)
        linkedin_config = config["platforms"]["linkedin"]
        print(f"[OK] Loaded config from {config_path}")
        print(f"     api_base: {linkedin_config.get('api_base')}")
        print(f"     api_version: {linkedin_config.get('api_version', 'not set')}")
        print(f"     enabled: {linkedin_config.get('enabled')}")
    except Exception as e:
        print(f"[FAIL] Could not load config: {e}")
        sys.exit(1)

    # Step 2: Verify Keychain access
    print()
    try:
        token = keychain_get(linkedin_config["keychain"]["access_token"])
        token_preview = token[:8] + "..." + token[-4:] if len(token) > 16 else "***"
        print(f"[OK] Access token retrieved from Keychain")
        print(f"     Preview: {token_preview}")
        print(f"     Length: {len(token)} chars")
    except RuntimeError as e:
        print(f"[FAIL] Keychain access failed: {e}")
        sys.exit(1)

    # Step 3: Initialize client
    print()
    try:
        client = LinkedInClient(linkedin_config)
        print(f"[OK] LinkedInClient initialized")
        print(f"     api_base: {client.api_base}")
        print(f"     api_version: {client.api_version}")
        print(f"     Linkedin-Version header: {client.session.headers.get('Linkedin-Version')}")
        print(f"     X-Restli-Protocol-Version: {client.session.headers.get('X-Restli-Protocol-Version')}")
    except Exception as e:
        print(f"[FAIL] Client init failed: {e}")
        sys.exit(1)

    # Step 4: Call /v2/userinfo (read-only, does NOT post anything)
    print()
    print("Calling GET /v2/userinfo ...")
    try:
        data = client.verify_token()
        print(f"[OK] Token is valid!")
        print()
        print("  User info:")
        print(f"     sub (member ID): {data.get('sub', 'N/A')}")
        print(f"     name:            {data.get('name', 'N/A')}")
        print(f"     given_name:      {data.get('given_name', 'N/A')}")
        print(f"     family_name:     {data.get('family_name', 'N/A')}")
        print(f"     email:           {data.get('email', 'N/A')}")
        print(f"     locale:          {data.get('locale', 'N/A')}")
        print(f"     picture:         {data.get('picture', 'N/A')[:60] + '...' if data.get('picture') and len(data.get('picture', '')) > 60 else data.get('picture', 'N/A')}")
        print()
        person_urn = f"urn:li:person:{data.get('sub', '')}"
        print(f"  Person URN: {person_urn}")
    except Exception as e:
        print(f"[FAIL] Token verification failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"       HTTP {e.response.status_code}: {e.response.text[:500]}")
            if e.response.status_code == 401:
                print()
                print("  The access token appears to be expired or invalid.")
                print("  LinkedIn OAuth2 tokens expire after 60 days.")
                print("  You need to re-authenticate to get a new token.")
        sys.exit(1)

    # Step 5: Token expiry warning
    print()
    token_expires_days = linkedin_config.get("token_expires_days", 60)
    print(f"  Token TTL (from config): {token_expires_days} days")
    print(f"  Note: LinkedIn does not expose token expiry via API.")
    print(f"  Track renewal dates manually or via the dashboard warning.")

    print()
    print("=" * 60)
    print("All checks passed. LinkedIn integration is ready.")
    print("=" * 60)


if __name__ == "__main__":
    main()
