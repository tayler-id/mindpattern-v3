# data/memory-db

> memory.db: 37 tables. Findings, editorial, user feedback, entity graph, embeddings.

## Core Table Groups

### Findings Pipeline
- `findings` — id, run_date, agent, title, summary, importance, category, source_url, source_name. FTS5 via `findings_fts`
- `findings_embeddings` — finding_id -> BLOB vector
- `sources` — url_domain (UNIQUE), display_name, hit_count, high_value_count, last_seen
- `patterns` / `patterns_embeddings` — theme, description, recurrence_count, first/last seen
- `claimed_topics` — run_date, agent, topic_hash, url (UNIQUE run_date+topic_hash). Prevents duplicate coverage

### Skills & Learning
- `skills` / `skills_embeddings` — domain, title, description, steps, difficulty, source_url
- `agent_notes` / `agent_notes_embeddings` — run_date, agent, note_type, content. Full-text searchable
- `validated_patterns` / `validated_patterns_embeddings` — pattern_key, distilled_rule, observation_count, status

### Editorial Pipeline
- `approval_reviews` — pipeline, stage, status, token (UNIQUE)
- `approval_items` — review_id (FK), platform, content, status, feedback
- `social_posts` / `social_posts_embeddings` — date, platform, content, gate2_action, posted
- `social_feedback` — date, platform, action, original_text, final_draft, edit_type
- `pending_posts` — platform, content, approved_at, post_after, posted

### User Interaction
- `user_feedback` / `feedback_embeddings` — email processing
- `user_preferences` — email, topic, weight (UNIQUE email+topic)
- `engagements` — platform, engagement_type, target_post_url, our_reply, status
- `social_metrics` — platform, platform_post_id, likes, comments, impressions

### Quality & Signals
- `signals` — source_pipeline, signal_type, topic, strength (0-1), evidence, run_date
- `run_quality` — run_date (UNIQUE), total_findings, unique_sources, overall_score, details_json
- `agent_checks` — run_date, agent, prompt_hash, check_name, passed, value, expected
- `failure_lessons` — run_date, category, what_went_wrong, lesson
- `editorial_corrections` — platform, original_text, approved_text, reason

### Entity Tracking
- `entity_graph` — entity_a, relationship, entity_b, finding_id. Knowledge graph

## Connected To

Written by [[orchestrator/runner]] phases. Read by [[orchestrator/evaluator]], [[orchestrator/agents]], [[social/pipeline]].

## Last Modified By Harness

Never — created 2026-04-01.
