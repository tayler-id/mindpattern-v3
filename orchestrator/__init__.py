"""Orchestrator modules for the mindpattern v3 pipeline.

Modules:
    newsletter  - Report validation and email delivery via Resend API
    evaluator   - Post-synthesis quality checks (deterministic, no LLM)
    observability - Pipeline monitoring, cost tracking, quality regression
    sync        - Fly.io synchronization (replaces sync-to-fly.sh)
"""
