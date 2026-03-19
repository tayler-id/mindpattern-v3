# How to Trigger the GitAgent User-Directed Topic

## Important Correction

The handoff note from the previous session stated that GitAgent is a "financial compliance system (FINRA, Fed, SEC, CFPB rules)." This is incorrect. GitAgent (https://www.gitagent.sh/) is an **open standard for defining AI agents as files in a git repository** — it has zero connection to financial regulation. The prepared brief reflects what GitAgent actually is.

## What's Prepared

The EIC-format topic brief is at:
```
data/social-drafts/user-directed-gitagent.json
```

This follows the exact schema that `social/eic.py:select_topic()` outputs — the same shape that `create_brief()` consumes downstream.

## How to Run It Through the Pipeline

The pipeline currently has no built-in "Mode 2" (User-Directed Synthesis) entry point. The EIC agent definition (`agents/eic.md`) and `social/eic.py` only support Mode 1 (autonomous topic selection from research findings). The handoff mentioned "EIC's Mode 2" but that mode does not exist in the codebase yet.

### Option A: Bypass EIC, Feed Directly to Creative Director (Recommended)

The simplest approach — skip EIC topic selection and inject the prepared topic directly into the brief creation step:

```python
import json
import sqlite3
from pathlib import Path
from social.eic import create_brief

# Load the prepared topic
with open("data/social-drafts/user-directed-gitagent.json") as f:
    topic = json.load(f)

# Connect to memory DB
import memory
db = memory.get_db(user_id="ramsay")

# Create the creative brief from the prepared topic
brief = create_brief(db=db, topic=topic, date_str="2026-03-15")

print(json.dumps(brief, indent=2))
```

Then manually continue the pipeline from step 4 (write_drafts):

```python
from social.writers import write_drafts
from social.critics import review_draft

# Load social config
with open("social-config.json") as f:
    config = json.load(f)

# Write drafts for enabled platforms
drafts = write_drafts(
    db=db,
    brief=brief,
    config=config.get("writers", {}),
    platforms=["bluesky", "linkedin"],
)

# Review with critics
for platform, draft in drafts.items():
    content = draft.get("content", draft) if isinstance(draft, dict) else draft
    review = review_draft(platform, content)
    print(f"{platform}: {review.get('verdict')}")
```

### Option B: Use Gate 1 Custom Topic Flow

The pipeline already supports injecting custom topics via Gate 1 (iMessage approval). When the normal pipeline runs:

1. EIC selects a topic
2. Gate 1 sends it to you via iMessage
3. Instead of replying "GO", you reply with a custom topic text
4. The pipeline sets `topic["anchor"]` to your custom text (line 160 of `social/pipeline.py`)

To use this: let the normal pipeline run (`python3 run.py --user ramsay`), wait for the Gate 1 iMessage, then reply with the GitAgent angle as free text.

Limitation: This only replaces the anchor text. It doesn't carry the full brief structure (reaction, sources, scores, etc.). The creative director would have to work from just the anchor.

### Option C: Write a Standalone Script (Most Complete)

```python
#!/usr/bin/env python3
"""Run the GitAgent user-directed topic through the full social pipeline."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

import memory
from social.pipeline import SocialPipeline
from social.eic import create_brief
from social.writers import write_drafts
from social.critics import review_draft, deterministic_validate, expedite
from social.approval import ApprovalGateway
from social.posting import BlueskyClient, LinkedInClient
from policies.engine import PolicyEngine

# Load configs
with open("social-config.json") as f:
    social_config = json.load(f)

with open("data/social-drafts/user-directed-gitagent.json") as f:
    topic = json.load(f)

db = memory.get_db(user_id="ramsay")
date_str = "2026-03-15"

# Step 1: Skip EIC — topic is pre-selected
print(f"Topic: {topic['anchor'][:100]}...")

# Step 2: Creative brief
brief = create_brief(db=db, topic=topic, date_str=date_str)
print(f"Brief angle: {brief.get('editorial_angle', 'none')[:100]}")

# Step 3: Write drafts
platforms = ["bluesky", "linkedin"]
drafts = write_drafts(
    db=db,
    brief=brief,
    config=social_config.get("writers", {}),
    platforms=platforms,
)

# Step 4: Critic review (single round)
for platform, draft in drafts.items():
    content = draft.get("content", draft) if isinstance(draft, dict) else draft
    review = review_draft(platform, content)
    print(f"Critic {platform}: {review.get('verdict')}")

# Step 5: Policy validation
policy = PolicyEngine.load_social()
for platform in list(drafts.keys()):
    content = drafts[platform]
    if isinstance(content, dict):
        content = content.get("content", content.get("text", str(content)))
    errors = policy.validate_social_post(platform, content)
    if errors:
        print(f"Policy violations for {platform}: {errors}")

# Step 6: Show drafts for manual review
print("\n=== DRAFTS FOR REVIEW ===\n")
for platform, draft in drafts.items():
    content = draft.get("content", draft) if isinstance(draft, dict) else draft
    print(f"--- {platform.upper()} ---")
    print(content)
    print()

print("Review the drafts above. To post, use the approval gateway or post manually.")
```

## Platforms

Currently enabled for posting:
- **Bluesky**: webdevdad.bsky.social (tested, working)
- **LinkedIn**: enabled but untested in v3
- **X**: disabled (no API key payment)
