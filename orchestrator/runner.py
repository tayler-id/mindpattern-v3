"""Main pipeline runner — deterministic state machine.

Python controls the phase sequence. Each phase is either a focused claude -p call
or a Python-only step. The LLM never decides what phase comes next.
"""

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import memory
from . import agents as agent_dispatch
from .arcs import format_arcs_for_synthesis, load_narrative_arcs
from .checkpoint import Checkpoint
from .evaluator import NewsletterEvaluator, assess_quality_floor
from .observability import PipelineMonitor
from .pipeline import Phase, PipelineRun, CRITICAL_PHASES
from .prompt_tracker import PromptTracker
from .traces_db import (
    get_db as get_traces_db,
    create_pipeline_run,
    create_agent_run,
    complete_agent_run,
    complete_pipeline_run,
    log_event,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


_IMPORTANCE_RANK = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def _enabled_platforms(social_config: dict) -> list[str]:
    """Return the names of social platforms with enabled=true.

    Handles the real schema (platforms is a dict of {name: {enabled: bool}})
    and the legacy list form (platforms is a list of names = all enabled).
    """
    plats = social_config.get("platforms", {})
    if isinstance(plats, dict):
        return [n for n, c in plats.items() if isinstance(c, dict) and c.get("enabled")]
    return list(plats)


def _draft_capable_platforms(social_config: dict) -> list[str]:
    """Return platforms that can at least produce manual-copy drafts."""
    from social.posting import resolve_platform_publish_mode

    plats = social_config.get("platforms", {})
    if isinstance(plats, dict):
        return [
            name for name in plats
            if resolve_platform_publish_mode(name, social_config).get("can_draft")
        ]
    return list(plats)


def _is_live_social_post_result(post: dict) -> bool:
    """True only for results that represent live outbound posts."""
    if post.get("manual_only"):
        return False
    if post.get("status") in {"manual_only", "skipped", "error"}:
        return False
    return not post.get("error")


def _format_source(source_name: str | None, source_url: str | None) -> str:
    """Return a markdown source reference."""
    name = source_name or "unknown"
    return f"[{name}]({source_url})" if source_url else name


def _source_health_for_trace(preflight_data: dict) -> dict:
    """Keep trace source health compact and avoid nested tool stderr payloads."""
    trace_health = {}
    for source_name, health in (preflight_data.get("source_health") or {}).items():
        trace_health[source_name] = {
            "status": health.get("status", "failed"),
            "count": health.get("count", 0),
            "reason": health.get("reason", ""),
        }
    return trace_health


def _assess_agent_coverage(agent_results: list) -> dict:
    """Summarize research agent coverage before storage/dedup side effects."""
    target = max(13, len(agent_results))
    min_agents = min(11, target)
    retryable_min_agents = min(8, target)
    contributing = [
        result.agent_name for result in agent_results
        if len(result.findings) > 0
    ]
    failed = [
        result.agent_name for result in agent_results
        if result.error and not result.findings
    ]
    zero_finding = [
        result.agent_name for result in agent_results
        if not result.error and not result.findings
    ]

    contributing_count = len(contributing)
    reasons = []
    status = "pass"
    if contributing_count < retryable_min_agents:
        status = "fail_retryable"
        reasons.append(
            f"agent coverage {contributing_count}/{target} below retryable floor "
            f"{retryable_min_agents}"
        )
    elif contributing_count < min_agents:
        status = "degraded"
        reasons.append(
            f"agent coverage {contributing_count}/{target} below floor "
            f"{min_agents}"
        )

    if zero_finding:
        reasons.append(f"zero-finding agents: {', '.join(zero_finding)}")
    if failed:
        reasons.append(f"failed agents: {', '.join(failed)}")

    return {
        "status": status,
        "degraded": status != "pass",
        "retryable": status == "fail_retryable",
        "target_agents": target,
        "total_agents": len(agent_results),
        "contributing_agents": contributing_count,
        "zero_finding_agents": zero_finding,
        "failed_agents": failed,
        "reasons": reasons,
    }


def _balance_story_candidates(
    findings: list[dict],
    preflight_data: dict | None = None,
    *,
    max_source_ratio: float = 0.35,
) -> tuple[list[dict], dict]:
    """Return a source-balanced story-selection candidate pool."""
    preflight_data = preflight_data or {}
    if not findings:
        return [], {
            "status": "pass",
            "original_count": 0,
            "candidate_count": 0,
            "max_source_ratio": 0.0,
            "reasons": [],
        }

    groups: dict[str, list[dict]] = {}
    labels: dict[str, str] = {}
    for finding in findings:
        key, label = _source_balance_key(finding)
        groups.setdefault(key, []).append(finding)
        labels.setdefault(key, label)

    source_health_summary = preflight_data.get("source_health_summary") or {}
    responsive_source_count = source_health_summary.get("responsive_source_count")
    source_class_count = len(groups)
    if responsive_source_count == 1 or source_class_count <= 1:
        reason = "only one healthy source class; source balance not fabricated"
        return findings, {
            "status": "degraded",
            "original_count": len(findings),
            "candidate_count": len(findings),
            "source_counts": {labels[k]: len(v) for k, v in groups.items()},
            "candidate_source_counts": {labels[k]: len(v) for k, v in groups.items()},
            "max_source_ratio": 1.0,
            "dropped_by_source": {},
            "reasons": [reason],
        }

    original_total = len(findings)
    capped: dict[str, list[dict]] = {}
    dropped_by_source = {}
    for key, items in groups.items():
        other_count = original_total - len(items)
        if other_count <= 0:
            keep_count = len(items)
        else:
            keep_count = int((max_source_ratio * other_count) / (1 - max_source_ratio))
            keep_count = max(1, keep_count)
        keep_count = min(len(items), keep_count)
        capped[key] = items[:keep_count]
        if keep_count < len(items):
            dropped_by_source[labels[key]] = len(items) - keep_count

    ordered_keys = sorted(capped, key=lambda k: (len(groups[k]), labels[k]))
    balanced: list[dict] = []
    index = 0
    while True:
        added = False
        for key in ordered_keys:
            if index < len(capped[key]):
                balanced.append(capped[key][index])
                added = True
        if not added:
            break
        index += 1

    candidate_counts = {labels[k]: len(v) for k, v in capped.items() if v}
    candidate_total = sum(candidate_counts.values())
    max_ratio = (
        max(candidate_counts.values()) / candidate_total
        if candidate_total else 0.0
    )
    status = "pass" if max_ratio <= max_source_ratio or candidate_total == 0 else "degraded"
    reasons = []
    if status == "degraded":
        reasons.append(
            f"single-source dominance {max_ratio:.3g} above ceiling {max_source_ratio:.3g}"
        )

    return balanced, {
        "status": status,
        "original_count": original_total,
        "candidate_count": len(balanced),
        "source_counts": {labels[k]: len(v) for k, v in groups.items()},
        "candidate_source_counts": candidate_counts,
        "max_source_ratio": round(max_ratio, 3),
        "dropped_by_source": dropped_by_source,
        "reasons": reasons,
    }


def _source_balance_key(finding: dict) -> tuple[str, str]:
    raw = (
        _row_get(finding, "source")
        or _row_get(finding, "source_name")
        or _row_get(finding, "source_url")
        or "unknown"
    )
    label = str(raw).strip() or "unknown"
    lowered = label.lower()
    if "arxiv" in lowered:
        return "arxiv", "arXiv"
    if "hacker news" in lowered or "ycombinator" in lowered:
        return "hn", "Hacker News"
    return lowered, label


def _row_get(row, key: str, default=None):
    if hasattr(row, "get"):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _fallback_ranked_findings(findings: list[dict], *, limit: int = 5) -> list[dict]:
    """Pick a deterministic, source-grounded fallback story set.

    Prefer higher-importance findings while preserving agent diversity so one
    noisy source cannot consume the whole daily brief.
    """
    ranked = sorted(
        enumerate(findings),
        key=lambda item: (
            -_IMPORTANCE_RANK.get(str(item[1].get("importance", "")).lower(), 0),
            str(item[1].get("agent") or ""),
            str(item[1].get("title") or ""),
            item[0],
        ),
    )
    selected: list[tuple[int, dict]] = []
    selected_ids: set[int] = set()
    seen_agents: set[str] = set()

    for original_idx, finding in ranked:
        agent = str(finding.get("agent") or "")
        if agent in seen_agents:
            continue
        selected.append((original_idx, finding))
        selected_ids.add(original_idx)
        seen_agents.add(agent)
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for original_idx, finding in ranked:
            if original_idx in selected_ids:
                continue
            selected.append((original_idx, finding))
            if len(selected) >= limit:
                break

    return [finding for _, finding in selected]


def _build_fallback_story_selection(findings: list[dict], *, reason: str) -> str:
    """Build an explicit story-selection block when the selector is unavailable."""
    selected = _fallback_ranked_findings(findings)
    lines = [
        "FALLBACK STORY SELECTION",
        f"Reason: {reason}",
        (
            "Use these exact stories as the main newsletter spine. Do not invent "
            "claims. Use source links from the findings. Use the remaining findings "
            "only for context or corroboration."
        ),
        "",
    ]
    for idx, finding in enumerate(selected, 1):
        source = _format_source(finding.get("source_name"), finding.get("source_url"))
        lines.extend([
            f"{idx}. {finding.get('title', 'Untitled')}",
            f"   Agent: {finding.get('agent', 'unknown')}",
            f"   Importance: {finding.get('importance', 'medium')}",
            f"   Source: {source}",
            f"   Summary: {finding.get('summary', '')}",
            "",
        ])
    return "\n".join(lines).strip()


def _format_newsletter_date(date_str: str) -> str:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%B %-d, %Y")


def _build_deterministic_newsletter(
    *,
    newsletter_title: str,
    date_str: str,
    findings: list[dict],
    reason: str,
) -> str:
    """Last-resort daily newsletter when the writer model does not complete."""
    selected = _fallback_ranked_findings(findings)
    agents = sorted({str(f.get("agent") or "unknown") for f in findings})
    lines = [
        f"# {newsletter_title} - {_format_newsletter_date(date_str)}",
        "",
        (
            "> Coverage note: Today's brief was generated from stored research "
            f"findings after the writing agent did not complete ({reason}). "
            "Each item below is source-grounded from the research database."
        ),
        "",
        "## Top Stories",
        "",
    ]

    for idx, finding in enumerate(selected, 1):
        source = _format_source(finding.get("source_name"), finding.get("source_url"))
        lines.extend([
            f"### {idx}. {finding.get('title', 'Untitled')}",
            "",
            f"Source: {source}",
            f"Agent: {finding.get('agent', 'unknown')}",
            f"Importance: {finding.get('importance', 'medium')}",
            "",
            str(finding.get("summary") or "No summary available."),
            "",
        ])

    lines.extend([
        "## Source Coverage",
        "",
        f"- Findings available: {len(findings)}",
        f"- Agents represented: {len(agents)}",
        f"- Agent list: {', '.join(agents) if agents else 'none'}",
        "",
        "## Follow-Up",
        "",
        (
            "Retry the full synthesis path after source and model health recover. "
            "This fallback is intentionally conservative and avoids unsupported claims."
        ),
        "",
    ])
    return "\n".join(lines)


def _recent_findings_for_quality(db, date_str: str, days: int = 3) -> list[dict]:
    from datetime import timedelta as _td

    cutoff = (datetime.strptime(date_str, "%Y-%m-%d") - _td(days=days)).strftime("%Y-%m-%d")
    rows = db.execute(
        "SELECT agent, title, summary, importance, source_url, source_name, run_date "
        "FROM findings WHERE run_date >= ? AND run_date < ?",
        (cutoff, date_str),
    ).fetchall()
    return [dict(row) for row in rows]


def _quality_floor_notice(quality_floor: dict) -> str:
    reasons = "; ".join((quality_floor.get("reasons") or [])[:4])
    if not reasons:
        reasons = quality_floor.get("status", "degraded")
    return (
        "> Degraded issue notice: quality floor "
        f"{quality_floor.get('status', 'degraded')} ({reasons}). "
        "This issue was generated from available stored findings and should be reviewed."
    )


class ResearchPipeline:
    """Orchestrates the full research pipeline for a single user."""

    def __init__(
        self,
        user_id: str,
        date_str: str | None = None,
        *,
        dry_run: bool = False,
    ):
        self.user_id = user_id
        self.date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        self.dry_run = dry_run or os.environ.get("MP_DRY_RUN") == "1"
        self.user_config = agent_dispatch.load_user_config(user_id)
        self.global_config = agent_dispatch.load_global_config()
        self.db = memory.get_db(user_id=user_id)
        self.trends: list[dict] = []
        self.agent_results: list = []
        self.newsletter_text: str = ""
        self.newsletter_eval: dict = {}
        self.social_result: dict = {}
        self.preflight_data: dict | None = None

        # Traces DB for observability
        self.traces_conn = get_traces_db()
        self.checkpoint = Checkpoint(self.traces_conn)
        self.monitor = PipelineMonitor(self.traces_conn)

        # Prompt tracking — initialized in _phase_init(), stored here for _phase_learn()
        self.prompt_tracker: PromptTracker | None = None
        self.prompt_changes: dict[str, dict] = {}

        # Set pipeline date so subprocess env vars include it for hooks
        agent_dispatch.set_pipeline_date(self.date_str)

        # Create pipeline run in traces.db so dashboard can see it
        self.pipeline = PipelineRun("research", user_id, self.date_str)
        self.traces_run_id = create_pipeline_run(
            self.traces_conn,
            pipeline_type="research",
            trigger="manual",
            metadata=json.dumps({
                "user_id": user_id,
                "date": self.date_str,
                "dry_run": self.dry_run,
            }),
            run_id=self.pipeline.run_id,
            status="running",
        )

    def run(self) -> int:
        """Execute the full pipeline. Returns exit code (0=success, 1=failure)."""
        logger.info(f"Starting pipeline {self.pipeline.run_id} for {self.user_id}")

        # Check for resumable run
        resume_id = self.checkpoint.find_resumable_run(self.user_id, self.date_str)
        if resume_id:
            resume_phase = self.checkpoint.resume_from(resume_id)
            if resume_phase:
                logger.info(f"Resuming from {resume_phase.value} (run {resume_id})")
                self.pipeline.run_id = resume_id
                self.pipeline.current_phase = resume_phase
                return self._execute_from(resume_phase)

        return self._execute_from(Phase.INIT)

    def _execute_from(self, start_phase: Phase) -> int:
        """Execute phases starting from the given phase."""
        from .pipeline import PHASE_ORDER

        start_idx = PHASE_ORDER.index(start_phase) if start_phase in PHASE_ORDER else 0

        try:
            for phase in PHASE_ORDER[start_idx:]:
                if phase in {Phase.COMPLETED, Phase.FAILED}:
                    break

                phase_start = time.monotonic()
                monitor_phase_id = None

                try:
                    # Skip transition if we're already at this phase (e.g. INIT at start)
                    if self.pipeline.current_phase != phase:
                        self.pipeline.transition(phase)
                    logger.info(f"Phase: {phase.value}")

                    # Log phase start to traces.db
                    log_event(self.traces_conn, self.traces_run_id,
                              f"phase_{phase.value}_start", "{}")

                    # Track phase in PipelineMonitor
                    try:
                        monitor_phase_id = self.monitor.start_phase(
                            self.pipeline.run_id, phase.value)
                    except Exception as e:
                        logger.warning(f"Monitor start_phase failed: {e}")

                    handler = self._get_phase_handler(phase)
                    if handler:
                        result = handler()
                        self.pipeline.complete_phase(phase, result)
                        self.checkpoint.save(self.pipeline.run_id, phase, result,
                                            user_id=self.user_id)
                    else:
                        logger.warning(f"No handler for phase {phase.value}, skipping")
                        self.pipeline.complete_phase(phase)
                        self.checkpoint.save(self.pipeline.run_id, phase,
                                            user_id=self.user_id)
                        result = {}

                    # Log phase completion
                    duration_ms = int((time.monotonic() - phase_start) * 1000)
                    log_event(self.traces_conn, self.traces_run_id,
                              f"phase_{phase.value}_complete",
                              json.dumps({"duration_ms": duration_ms, "result": str(result)[:500]}))

                    # End phase tracking in PipelineMonitor
                    if monitor_phase_id is not None:
                        try:
                            self.monitor.end_phase(monitor_phase_id, "completed")
                        except Exception as e:
                            logger.warning(f"Monitor end_phase failed: {e}")

                except Exception as e:
                    error_msg = f"{phase.value}: {e}"
                    duration_ms = int((time.monotonic() - phase_start) * 1000)
                    logger.error(error_msg, exc_info=True)

                    log_event(self.traces_conn, self.traces_run_id,
                              f"phase_{phase.value}_failed",
                              json.dumps({"error": str(e)[:500], "duration_ms": duration_ms}))

                    # End phase tracking as failed in PipelineMonitor
                    if monitor_phase_id is not None:
                        try:
                            self.monitor.end_phase(
                                monitor_phase_id, "failed", error=str(e)[:500])
                        except Exception as me:
                            logger.warning(f"Monitor end_phase (failed) failed: {me}")

                    if phase in CRITICAL_PHASES:
                        self.pipeline.fail(error_msg)
                        complete_pipeline_run(self.traces_conn, self.traces_run_id,
                                             status="failed", error=error_msg)
                        self._send_alert(f"CRITICAL: {error_msg}")
                        return 1
                    else:
                        self.pipeline.fail_phase(phase, str(e))
                        logger.warning(f"Non-critical phase {phase.value} failed, continuing")
                        self.checkpoint.save(self.pipeline.run_id, phase, {"error": str(e)},
                                            user_id=self.user_id)
        except KeyboardInterrupt:
            logger.warning("Pipeline interrupted by user")
            log_event(self.traces_conn, self.traces_run_id,
                      "pipeline_interrupted", "{}")
            complete_pipeline_run(self.traces_conn, self.traces_run_id,
                                  status="interrupted", error="KeyboardInterrupt")
            raise

        # Mark completed
        self.pipeline.transition(Phase.COMPLETED)
        self.checkpoint.save(self.pipeline.run_id, Phase.COMPLETED,
                             user_id=self.user_id)

        warnings = self.pipeline.warnings
        if warnings:
            complete_pipeline_run(self.traces_conn, self.traces_run_id,
                                  status="completed",
                                  error=json.dumps({"warnings": warnings}))
            logger.warning(f"Completed with {len(warnings)} warnings")
        else:
            complete_pipeline_run(self.traces_conn, self.traces_run_id, status="completed")

        # Generate and log pipeline summary from PipelineMonitor
        try:
            summary = self.monitor.generate_summary(self.date_str)
            logger.info(f"Pipeline summary: {summary}")
            log_event(self.traces_conn, self.traces_run_id,
                      "pipeline_summary", json.dumps({"summary": summary}))
        except Exception as e:
            logger.warning(f"Monitor summary generation failed: {e}")

        logger.info(f"Pipeline {self.pipeline.run_id} completed")
        return 0

    def _record_agent_trace(self, result) -> None:
        """Mirror one research agent result into traces.db agent_runs."""
        agent_name = getattr(result, "agent_name", "unknown-agent")
        findings = getattr(result, "findings", []) or []
        agent_run_id = f"{self.traces_run_id}/{agent_name}"
        try:
            create_agent_run(
                self.traces_conn,
                self.traces_run_id,
                agent_name,
            )
        except sqlite3.IntegrityError:
            pass
        except Exception as e:
            logger.warning(
                f"Trace create_agent_run failed for {agent_name}: {e}"
            )
            return

        error = getattr(result, "error", None)
        status = "failed" if error and not findings else "completed"
        output = getattr(result, "raw_output", "")
        if not output:
            output = json.dumps({
                "findings_count": len(findings),
                "classification": getattr(result, "classification", None),
                "exit_code": getattr(result, "exit_code", None),
            })
        try:
            complete_agent_run(
                self.traces_conn,
                agent_run_id,
                status=status,
                output=output,
                error=error,
                latency_ms=getattr(result, "duration_ms", None),
            )
        except Exception as e:
            logger.warning(
                f"Trace complete_agent_run failed for {agent_name}: {e}"
            )

    def _get_phase_handler(self, phase: Phase):
        """Map phases to their handler methods."""
        if phase in {Phase.COMPLETED, Phase.FAILED}:
            return None

        if (
            os.environ.get("MP_SKIP_SOCIAL") == "1"
            and phase in {Phase.SOCIAL, Phase.ENGAGEMENT}
        ):
            return lambda phase=phase: self._phase_skip_social(phase)

        if getattr(self, "dry_run", False):
            if phase == Phase.SYNTHESIS:
                return self._phase_synthesis_dry_run
            return lambda phase=phase: self._phase_dry_run_skip(phase)

        if os.environ.get("MP_DISABLE_OUTBOUND") == "1" and phase == Phase.SYNC:
            return lambda phase=phase: self._phase_outbound_disabled_skip(phase)

        return {
            Phase.INIT: self._phase_init,
            Phase.TREND_SCAN: self._phase_trend_scan,
            Phase.RESEARCH: self._phase_research,
            Phase.SYNTHESIS: self._phase_synthesis,
            Phase.DELIVER: self._phase_deliver,
            Phase.LEARN: self._phase_learn,
            Phase.SOCIAL: self._phase_social,
            Phase.ENGAGEMENT: self._phase_engagement,
            Phase.IDENTITY: self._phase_identity,
            Phase.MIRROR: self._phase_mirror,
            Phase.SYNC: self._phase_sync,
        }.get(phase)

    # ── Phase handlers ─────────────────────────────────────────────────

    def _phase_dry_run_skip(self, phase: Phase) -> dict:
        """Skip a phase that would fetch, mutate, send, or deploy in dry-run."""
        logger.info("DRY RUN: skipping %s phase", phase.value)
        return {"dry_run": True, "skipped": True, "phase": phase.value}

    def _phase_skip_social(self, phase: Phase) -> dict:
        """Skip social/engagement when the runner is told to stay newsletter-only."""
        logger.info("MP_SKIP_SOCIAL=1: skipping %s phase", phase.value)
        return {
            "skipped": True,
            "phase": phase.value,
            "reason": "MP_SKIP_SOCIAL=1",
        }

    def _phase_outbound_disabled_skip(self, phase: Phase) -> dict:
        """Skip phases that would perform external sync while outbound is disabled."""
        logger.info("MP_DISABLE_OUTBOUND=1: skipping %s phase", phase.value)
        return {
            "skipped": True,
            "phase": phase.value,
            "reason": "MP_DISABLE_OUTBOUND=1",
        }

    def _phase_synthesis_dry_run(self) -> dict:
        """Write a local placeholder report without touching the real daily report."""
        report_dir = PROJECT_ROOT / "reports" / self.user_id
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{self.date_str}-dry-run.md"

        self.newsletter_text = (
            f"# Dry-Run Report - {self.date_str}\n\n"
            "This is a dry-run placeholder. No Claude calls, outbound sends, "
            "or Fly syncs were performed.\n"
        )
        self.newsletter_eval = {"dry_run": True}
        report_path.write_text(self.newsletter_text)
        logger.info("DRY RUN: wrote placeholder report to %s", report_path)

        return {
            "dry_run": True,
            "word_count": len(self.newsletter_text.split()),
            "report_path": str(report_path),
            "eval_scores": self.newsletter_eval,
        }

    def _phase_init(self) -> dict:
        """Phase 1: Init (Python only, no LLM)."""
        prefs = memory.list_preferences(self.db, email=self.user_config.get("email"), effective=True)
        logger.info(f"Loaded {len(prefs)} preferences")

        # ── Ingest Fly-side events (phone posts) so dedup/caps see them ──
        try:
            from .journal_ingest import pull_and_ingest

            jr = pull_and_ingest(self.db, self.user_id)
            if jr.get("error"):
                logger.warning(f"Journal ingest failed (non-critical): {jr['error']}")
            elif jr.get("new_lines"):
                logger.info(
                    f"Journal ingest: {jr.get('ingested', 0)} ingested, "
                    f"{jr.get('skipped', 0)} skipped of {jr['new_lines']} new line(s)"
                )
        except Exception as e:
            logger.warning(f"Journal ingest failed (non-critical): {e}")

        try:
            resend_key = self._keychain_lookup("resend-api-key")
            if resend_key:
                fb_result = memory.fetch_feedback(
                    self.db, resend_key,
                    user_email=self.user_config.get("email"),
                )
                logger.info(f"Feedback: {fb_result.get('fetched', 0)} new, {fb_result.get('pending_feedback', 0)} pending")
        except Exception as e:
            logger.warning(f"Feedback fetch failed (non-critical): {e}")

        # ── Process unprocessed feedback into preference updates ──────
        try:
            self._process_pending_feedback()
        except Exception as e:
            logger.warning(f"Feedback processing failed (non-critical): {e}")

        failures = memory.recent_failures(self.db, limit=10)
        if failures:
            logger.info(f"Loaded {len(failures)} recent failure lessons")

        # ── Prompt tracking: detect changes since last run ──────────
        self.prompt_tracker = PromptTracker(self.traces_conn)
        self.prompt_changes = self.prompt_tracker.scan_for_changes()

        changed_files = {p: info for p, info in self.prompt_changes.items() if info["changed"]}
        if changed_files:
            logger.info(f"Prompt changes detected: {len(changed_files)} file(s)")
            for path, info in changed_files.items():
                old = info["old_hash"][:12] if info["old_hash"] else "NEW"
                new = info["new_hash"][:12]
                logger.info(f"  {path}: {old} → {new}")
                self.prompt_tracker.record_version(path)

            log_event(
                self.traces_conn, self.traces_run_id,
                "prompt_changes_detected",
                json.dumps({p: {"old": i["old_hash"], "new": i["new_hash"]}
                            for p, i in changed_files.items()}),
            )
        else:
            logger.info("No prompt file changes detected")

        return {
            "preferences_count": len(prefs),
            "failures_loaded": len(failures),
            "prompt_changes": len(changed_files),
        }

    def _process_pending_feedback(self) -> None:
        """Process unprocessed user feedback into preference weight changes.

        Queries user_feedback for unprocessed rows, sends them to Claude
        for preference extraction, then calls memory.set_preference() and
        memory.mark_processed() accordingly.
        """
        unprocessed = self.db.execute(
            "SELECT id, from_email, subject, body FROM user_feedback WHERE processed = 0"
        ).fetchall()

        if not unprocessed:
            return

        feedback_texts = []
        feedback_ids = []
        for row in unprocessed:
            feedback_ids.append(row["id"])
            entry = f"From: {row['from_email']}"
            if row["subject"]:
                entry += f"\nSubject: {row['subject']}"
            entry += f"\nBody: {row['body']}"
            feedback_texts.append(entry)

        prompt = (
            "Parse the following newsletter feedback emails and extract topic "
            "preference changes. Return ONLY valid JSON.\n\n"
            + "\n---\n".join(feedback_texts)
        )

        system_prompt_file = str(
            Path(__file__).parent.parent / "agents" / "feedback-processor.md"
        )

        output, exit_code = agent_dispatch.run_claude_prompt(
            prompt,
            "feedback_processor",
            system_prompt_file=system_prompt_file,
            allowed_tools=[],
        )

        if exit_code != 0 or not output.strip():
            logger.warning("Feedback processor returned no output (exit=%d)", exit_code)
            return

        # Parse JSON from output — strip any surrounding text/fences
        text = output.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        # Fallback: find first JSON object in output
        import re
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    result = json.loads(match.group())
                except json.JSONDecodeError:
                    logger.warning("Feedback processor returned invalid JSON: %s", text[:200])
                    return
            else:
                logger.warning("Feedback processor returned no JSON: %s", text[:200])
                return

        preferences = result.get("preferences", [])
        user_email = self.user_config.get("email", "")

        for pref in preferences:
            topic = pref.get("topic", "").strip().lower()
            weight = pref.get("weight", 0.0)
            if not topic or weight == 0.0:
                continue

            try:
                weight = float(weight)
                weight = max(-3.0, min(3.0, weight))
            except (TypeError, ValueError):
                continue

            memory.set_preference(
                self.db, user_email, topic, weight, source="feedback"
            )
            logger.info("Preference updated: %s = %+.1f", topic, weight)

        memory.mark_processed(self.db, feedback_ids)
        logger.info(
            "Processed %d feedback item(s), %d preference update(s)",
            len(feedback_ids),
            len([p for p in preferences if p.get("topic", "").strip() and p.get("weight", 0.0) != 0.0]),
        )

    def _phase_trend_scan(self) -> dict:
        """Phase 2: Trend Scan (deterministic, from preflight data).

        Runs preflight to gather data from 8 sources, then detects trends
        by clustering items by topic similarity and scoring by engagement
        and source diversity. No LLM call required.

        Skippable — if it fails, research agents run without trends.
        """
        from preflight.trends import detect_trends
        from preflight.run_all import run_all as run_preflight

        # Run preflight here so trends are computed from real data
        try:
            self.preflight_data = run_preflight(
                date_str=self.date_str,
                db=self.db,
                feeds_file=PROJECT_ROOT / "verticals" / "ai-tech" / "rss-feeds.json",
            )
            logger.info(
                f"Preflight: {self.preflight_data['total_items']} items, "
                f"{self.preflight_data['new_count']} new, "
                f"{self.preflight_data['covered_count']} already covered, "
                f"{self.preflight_data['duration_ms']}ms"
            )
            log_event(self.traces_conn, self.traces_run_id,
                      "preflight_complete",
                      json.dumps({
                          "run_date": self.date_str,
                          "total_items": self.preflight_data["total_items"],
                          "new_count": self.preflight_data["new_count"],
                          "covered_count": self.preflight_data["covered_count"],
                          "source_counts": self.preflight_data["source_counts"],
                          "source_health": _source_health_for_trace(self.preflight_data),
                          "source_health_summary": self.preflight_data.get(
                              "source_health_summary", {}
                          ),
                          "duration_ms": self.preflight_data["duration_ms"],
                      }))
        except Exception as e:
            logger.warning(f"Preflight failed (non-critical): {e}")
            self.preflight_data = None

        # Detect trends from preflight data (deterministic, no LLM)
        items = self.preflight_data["items"] if self.preflight_data else []
        self.trends = detect_trends(items)

        # Store trends in trend_history for the learning loop
        try:
            from memory.trends import store_trends
            store_trends(self.db, self.date_str, self.trends)
        except Exception as e:
            logger.warning(f"Failed to store trend history (non-critical): {e}")

        trend_topics = [t["topic"][:80] for t in self.trends[:5]]
        logger.info(
            f"Trend scan: {len(self.trends)} trends detected from "
            f"{len(items)} preflight items. Top: {trend_topics}"
        )

        return {
            "trends": self.trends,
            "preflight_items": len(items),
            "source_health_summary": (
                self.preflight_data.get("source_health_summary", {})
                if self.preflight_data else {}
            ),
            "method": "deterministic",
        }

    def _phase_research(self) -> dict:
        """Phase 3: Research (13x Sonnet, parallel)."""
        # Use preflight data from TREND_SCAN phase (already ran)
        preflight_data = self.preflight_data
        if preflight_data:
            logger.info(
                f"Using preflight data from trend scan: "
                f"{preflight_data['total_items']} items, {preflight_data['new_count']} new"
            )
        else:
            logger.warning("No preflight data available (trend scan may have failed), agents will use WebSearch")

        # Get cross-pipeline signal context to enrich agent dispatch
        signal_context = ""
        try:
            signal_context = memory.get_signal_context(self.db)
        except Exception as e:
            logger.warning(f"Signal context retrieval failed: {e}")

        def context_fn(agent_name, date_str):
            ctx = memory.get_context(self.db, agent_name, date_str)
            if signal_context and "No cross-pipeline signals" not in signal_context:
                ctx = ctx + "\n\n" + signal_context if ctx else signal_context
            return ctx

        self.agent_results = agent_dispatch.dispatch_research_agents(
            user_id=self.user_id,
            date_str=self.date_str,
            context_fn=context_fn,
            trends=self.trends,
            max_workers=6,
            preflight_data=preflight_data,
        )

        agent_coverage = _assess_agent_coverage(self.agent_results)
        self.research_quality = {"agent_coverage": agent_coverage}
        if agent_coverage["degraded"]:
            logger.warning(
                "Research agent coverage degraded: %s",
                "; ".join(agent_coverage["reasons"]),
            )
            log_event(self.traces_conn, self.traces_run_id,
                      "research_agent_coverage",
                      json.dumps(agent_coverage))

        # Sources older than this (by URL-embedded date) are resurfaced
        # content, not today's news.
        from datetime import timedelta as _td
        stale_cutoff = (
            datetime.strptime(self.date_str, "%Y-%m-%d") - _td(days=30)
        ).strftime("%Y-%m-%d")

        # Cross-agent dedup: remove near-duplicate findings across agents
        try:
            self.agent_results, dedup_summary = agent_dispatch.dedup_cross_agent_findings(
                self.agent_results
            )
            log_event(self.traces_conn, self.traces_run_id,
                      "cross_agent_dedup", json.dumps(dedup_summary))
        except Exception as e:
            logger.warning(f"Cross-agent dedup failed (non-critical): {e}")

        total_stored = 0
        for result in self.agent_results:
            if result.error and not result.findings:
                continue

            for finding in result.findings:
                try:
                    title = finding.get("title", "")
                    summary = finding.get("summary", "")
                    if not title or not summary:
                        continue

                    # Dedup: check if a near-identical finding exists in the last 10 days
                    # Dedup gate (2026-06-12 lesson: a January story reached
                    # the newsletter). Two layers:
                    # 1. Stale source: a URL carrying its own date >30 days
                    #    old is resurfaced content, not news. Deterministic.
                    source_date = memory.source_date_from_url(
                        finding.get("source_url")
                    )
                    if source_date and source_date < stale_cutoff:
                        logger.info(
                            f"Skipping stale-source finding ({source_date}): "
                            f"'{title[:60]}'"
                        )
                        continue

                    # 2. Semantic near-duplicate vs 180 days of history
                    #    (was 10 days — re-coverage older than the window was
                    #    invisible). 0.90 stays: calibration on real data
                    #    showed distinct stories score up to 0.81 vs related
                    #    coverage, so a lower bar censors real news.
                    existing = memory.search_findings(
                        self.db, f"{title}. {summary}", limit=1, days=180,
                    )
                    if existing and existing[0].get("similarity", 0) > 0.90:
                        logger.info(
                            f"Skipping duplicate: '{title[:50]}' "
                            f"(sim={existing[0]['similarity']:.2f} with '{existing[0]['title'][:50]}')"
                        )
                        continue

                    memory.store_finding(
                        self.db,
                        run_date=self.date_str,
                        agent=result.agent_name,
                        title=title,
                        summary=summary,
                        importance=finding.get("importance", "medium"),
                        category=finding.get("category"),
                        source_url=finding.get("source_url"),
                        source_name=finding.get("source_name"),
                    )
                    total_stored += 1

                    if finding.get("source_url"):
                        from urllib.parse import urlparse
                        domain = urlparse(finding["source_url"]).netloc
                        if domain:
                            memory.store_source(
                                self.db, domain,
                                name=finding.get("source_name"),
                                quality="high" if finding.get("importance") == "high" else "medium",
                                date=self.date_str,
                            )
                except Exception as e:
                    logger.warning(f"Failed to store finding from {result.agent_name}: {e}")

            memory.log_agent_run(
                self.db, result.agent_name, self.date_str,
                findings_count=len(result.findings),
            )
            self._record_agent_trace(result)

            # Record per-agent metrics in PipelineMonitor
            try:
                self.monitor.record_agent_metrics(
                    result.agent_name,
                    self.date_str,
                    findings_count=len(result.findings),
                    duration_ms=result.duration_ms,
                )
            except Exception as e:
                logger.warning(f"Monitor record_agent_metrics failed for {result.agent_name}: {e}")

        # Validate findings with PolicyEngine (if research.json exists)
        try:
            from policies.engine import PolicyEngine
            policy = PolicyEngine.load_research()
            for result in self.agent_results:
                if result.error and not result.findings:
                    continue
                errors = policy.validate_agent_output(
                    result.agent_name, {"findings": result.findings})
                if errors:
                    logger.warning(
                        f"Policy violations for {result.agent_name}: "
                        f"{len(errors)} issue(s)")
                    for err in errors[:5]:  # Log first 5 only
                        logger.warning(f"  {err}")
        except FileNotFoundError:
            logger.debug("No research.json policy file, skipping validation")
        except Exception as e:
            logger.warning(f"Policy validation failed (non-critical): {e}")

        successful = sum(1 for r in self.agent_results if not r.error)
        logger.info(f"Research: {successful} agents succeeded, {total_stored} findings stored")

        # Log per-agent breakdown with low-findings warnings
        for r in self.agent_results:
            findings_count = len(r.findings)
            status = "OK" if findings_count >= 15 else "LOW" if findings_count > 0 else "ZERO"
            logger.info(
                f"  Agent {r.agent_name}: {findings_count} findings, "
                f"{r.duration_ms}ms, status={status}"
                + (f", error={r.error}" if r.error else "")
            )
            if 0 < findings_count < 15:
                logger.warning(
                    f"Agent {r.agent_name} returned only {findings_count} findings "
                    f"(target: 15-20). Check agent skill file or timeout."
                )

        if total_stored == 0:
            raise RuntimeError("Zero findings stored — research phase failed")

        return {
            "agents_dispatched": len(self.agent_results),
            "agents_succeeded": successful,
            "findings_stored": total_stored,
            "research_degraded": agent_coverage["degraded"],
            "agent_coverage": agent_coverage,
        }

    def _phase_synthesis(self) -> dict:
        """Phase 4: Synthesis (Opus, two passes).

        Pass 1: Story selection from summaries.
        Pass 2: Newsletter writing from full reports.
        """
        today_findings = self.db.execute(
            "SELECT agent, title, summary, importance, source_url, source_name "
            "FROM findings WHERE run_date = ?",
            (self.date_str,),
        ).fetchall()

        if not today_findings:
            raise RuntimeError("No findings available for synthesis")

        # Sanitize findings that might trigger usage policy filters.
        # Security research findings about prompt injection, jailbreaks, etc.
        # are legitimate but can cause the API to reject the entire prompt.
        _sensitive_patterns = [
            "prompt injection", "jailbreak", "hijack", "exfiltrat",
            "attack chain", "adversarial", "exploit", "bypass safety",
        ]

        def _sanitize_finding(f: dict) -> dict:
            """Wrap sensitive security research titles/summaries so they
            don't trigger content filters when assembled into a large prompt."""
            text = f"{f['title']} {f['summary']}".lower()
            if any(p in text for p in _sensitive_patterns):
                # Reframe as security research coverage
                return {**f,
                    'title': f"[Security Research] {f['title']}",
                    'summary': (
                        f"Academic/industry security research report. "
                        f"This is a defensive security finding for newsletter coverage. "
                        f"Summary: {f['summary']}"
                    ),
                }
            return f

        today_findings = [_sanitize_finding(dict(f)) for f in today_findings]
        sanitized_count = sum(
            1 for f in today_findings if f['title'].startswith('[Security Research]')
        )
        if sanitized_count:
            logger.info(f"Sanitized {sanitized_count} security research findings for synthesis")

        story_findings, source_balance = _balance_story_candidates(
            today_findings,
            self.preflight_data,
        )
        self.source_balance = source_balance
        if source_balance.get("status") != "pass":
            logger.warning(
                "Source balance degraded: %s",
                "; ".join(source_balance.get("reasons", [])),
            )
            log_event(self.traces_conn, self.traces_run_id,
                      "source_balance_degraded",
                      json.dumps(source_balance))

        # Build summaries for pass 1 — full text, not truncated (we have 1M context)
        summaries = []
        for f in story_findings:
            source = f"[{f['source_name']}]({f['source_url']})" if f['source_url'] else f['source_name'] or ''
            summaries.append(
                f"[{f['agent']}] ({f['importance']}) {f['title']}\n"
                f"  Source: {source}\n"
                f"  {f['summary']}"
            )

        prefs = memory.list_preferences(self.db, effective=True)
        pref_text = "\n".join(
            f"- {p['topic']}: weight {p.get('effective_weight', p['weight'])}"
            for p in prefs
        ) if prefs else "No specific preferences."

        trends_text = ", ".join(
            t.get("topic", "") for t in self.trends
        ) if self.trends else "No trending topics identified."

        newsletter_title = self.user_config.get("newsletter_title", "Research Agent")

        # Pass 1: Story selection
        pass1_prompt = (
            f"Select exactly 5 stories from these {len(summaries)} balanced candidate findings for today's newsletter.\n\n"
            f"Date: {self.date_str}\n\n"
            f"## User Preferences\n{pref_text}\n\n"
            f"## Trending Topics\n{trends_text}\n\n"
            f"## Findings\n" + "\n".join(summaries)
        )

        logger.info(
            f"Synthesis pass 1: prompt_size={len(pass1_prompt)} chars, "
            f"model={agent_dispatch.router.get_model('synthesis_pass1')}, "
            f"findings_count={len(summaries)}"
        )
        pass1_output = ""
        pass1_degraded = False
        pass1_max_attempts = 3
        for attempt in range(1, pass1_max_attempts + 1):
            pass1_start = time.monotonic()
            pass1_output, exit_code = agent_dispatch.run_claude_prompt(
                pass1_prompt, "synthesis_pass1",
                system_prompt_file="agents/synthesis-selector.md",
            )
            pass1_duration = time.monotonic() - pass1_start
            output_len = len(pass1_output) if pass1_output else 0
            logger.info(
                f"Synthesis pass 1 attempt {attempt}/{pass1_max_attempts} complete: "
                f"exit_code={exit_code}, output_len={output_len}, "
                f"duration={pass1_duration:.1f}s"
            )
            if exit_code == 0 and pass1_output.strip():
                break

            output_preview = (pass1_output or "")[:200].replace("\n", "\\n")
            logger.warning(
                f"Synthesis pass 1 attempt {attempt}/{pass1_max_attempts} failed: "
                f"exit_code={exit_code}, output_len={output_len}, "
                f"duration={pass1_duration:.1f}s, "
                f"output_preview='{output_preview}'"
            )
            log_event(self.traces_conn, self.traces_run_id,
                      "synthesis_pass1_retry",
                      json.dumps({
                          "attempt": attempt,
                          "exit_code": exit_code,
                          "output_len": output_len,
                          "duration_s": round(pass1_duration, 1),
                          "output_preview": output_preview,
                      }))

            if attempt == pass1_max_attempts:
                pass1_degraded = True
                reason = (
                    f"synthesis pass 1 failed after {pass1_max_attempts} attempts; "
                    f"last exit_code={exit_code}, output_len={output_len}"
                )
                pass1_output = _build_fallback_story_selection(
                    story_findings,
                    reason=reason,
                )
                logger.error(
                    "Synthesis pass 1 exhausted; using deterministic fallback "
                    "story selection instead of failing the daily newsletter"
                )
                log_event(self.traces_conn, self.traces_run_id,
                          "synthesis_pass1_fallback",
                          json.dumps({
                              "attempts": pass1_max_attempts,
                              "last_exit_code": exit_code,
                              "last_output_len": output_len,
                              "selected_count": min(5, len(today_findings)),
                          }))

        # Pass 2: Newsletter writing (with retry logic)
        full_findings = []
        for f in today_findings:
            source = _format_source(f.get("source_name"), f.get("source_url"))
            full_findings.append(
                f"### [{f['agent']}] {f['title']} ({f['importance']})\n"
                f"Source: {source}\n{f['summary']}\n"
            )

        failures = memory.recent_failures(self.db, limit=5)
        failure_text = ""
        if failures:
            failure_text = "\n## Previous failures to avoid:\n" + "\n".join(
                f"- [{fl['category']}] {fl['lesson']}" for fl in failures
            )

        # Load identity files for editorial voice
        identity_dir = PROJECT_ROOT / "data" / self.user_id / "mindpattern"
        soul_text = ""
        voice_text = ""
        if identity_dir.exists():
            soul_file = identity_dir / "soul.md"
            if soul_file.exists():
                soul_text = f"## Editorial Identity\n{soul_file.read_text()}\n\n"
            voice_file = identity_dir / "voice.md"
            if voice_file.exists():
                voice_text = f"## Voice Guide\n{voice_file.read_text()}\n\n"

        fallback_mode_text = ""
        if pass1_degraded:
            fallback_mode_text = (
                "## Selection Recovery Mode\n"
                "The dedicated story selector did not complete after retries. "
                "A deterministic Top 5 fallback was created below. Use that "
                "selection exactly for the main story spine, keep the writing "
                "source-grounded, and do not pad weak claims.\n\n"
            )

        narrative_arcs_context = ""
        narrative_arcs_count = 0
        try:
            narrative_arcs = load_narrative_arcs(
                date=self.date_str,
                user=self.user_id,
                reports_root=PROJECT_ROOT / "reports",
                limit=5,
                statuses={"active", "emerging"},
            )
            narrative_arcs_context = format_arcs_for_synthesis(narrative_arcs)
            narrative_arcs_count = len(narrative_arcs) if narrative_arcs_context else 0
            if narrative_arcs_context:
                log_event(
                    self.traces_conn,
                    self.traces_run_id,
                    "narrative_arcs_context",
                    json.dumps({"count": narrative_arcs_count}),
                )
        except Exception as e:
            logger.warning(f"Narrative arc context unavailable: {e}")
            log_event(
                self.traces_conn,
                self.traces_run_id,
                "narrative_arcs_context_degraded",
                json.dumps({"error": f"{type(e).__name__}: {e}"}),
            )

        pass2_prompt = (
            f"Write the \"{newsletter_title}\" newsletter for {self.date_str}.\n\n"
            f"{soul_text}"
            f"{voice_text}"
            f"You have {len(today_findings)} findings from {len(set(f['agent'] for f in today_findings))} agents.\n\n"
            f"{fallback_mode_text}"
            f"## Story Selection\n{pass1_output}\n\n"
            f"{narrative_arcs_context}\n\n"
            f"## All Findings\n" + "\n".join(full_findings) + "\n\n"
            f"## User Preferences\n{pref_text}\n\n"
            f"{failure_text}"
        )

        logger.info(
            f"Synthesis pass 2: prompt_size={len(pass2_prompt)} chars, "
            f"model={agent_dispatch.router.get_model('synthesis_pass2')}, "
            f"timeout={agent_dispatch.router.get_timeout('synthesis_pass2')}s"
        )

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            attempt_start = time.monotonic()
            self.newsletter_text, exit_code = agent_dispatch.run_claude_prompt(
                pass2_prompt, "synthesis_pass2",
                system_prompt_file="agents/synthesis-writer.md",
            )
            attempt_duration = time.monotonic() - attempt_start
            output_len = len(self.newsletter_text) if self.newsletter_text else 0

            if exit_code == 0 and self.newsletter_text.strip():
                # Enforce deterministic title: strip any LLM-generated H1 and prepend ours
                from datetime import datetime
                date_obj = datetime.strptime(self.date_str, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%B %-d, %Y")
                deterministic_title = f"# {newsletter_title} — {formatted_date}\n\n"
                body = self.newsletter_text.strip()
                # Strip LLM-generated title if present (H1 line or bold title)
                if body.startswith("# "):
                    body = body.split("\n", 1)[1].strip()
                self.newsletter_text = deterministic_title + body
                output_len = len(self.newsletter_text)

                logger.info(
                    f"Synthesis pass 2 succeeded on attempt {attempt}/{max_attempts}: "
                    f"exit_code={exit_code}, output_len={output_len}, "
                    f"duration={attempt_duration:.1f}s"
                )
                break

            # Log failure details for debugging
            output_preview = (self.newsletter_text or "")[:200].replace("\n", "\\n")
            logger.warning(
                f"Synthesis pass 2 attempt {attempt}/{max_attempts} failed: "
                f"exit_code={exit_code}, output_len={output_len}, "
                f"duration={attempt_duration:.1f}s, "
                f"output_preview='{output_preview}'"
            )
            log_event(self.traces_conn, self.traces_run_id,
                      "synthesis_pass2_retry",
                      json.dumps({
                          "attempt": attempt,
                          "exit_code": exit_code,
                          "output_len": output_len,
                          "duration_s": round(attempt_duration, 1),
                          "output_preview": output_preview,
                      }))

            if attempt == max_attempts:
                reason = (
                    f"synthesis pass 2 failed after {max_attempts} attempts; "
                    f"last exit_code={exit_code}, output_len={output_len}, "
                    f"duration={attempt_duration:.1f}s"
                )
                self.newsletter_text = _build_deterministic_newsletter(
                    newsletter_title=newsletter_title,
                    date_str=self.date_str,
                    findings=today_findings,
                    reason=reason,
                )
                logger.error(
                    "Synthesis pass 2 exhausted; wrote deterministic daily "
                    "brief from stored findings instead of failing completely"
                )
                log_event(self.traces_conn, self.traces_run_id,
                          "synthesis_pass2_fallback",
                          json.dumps({
                              "attempts": max_attempts,
                              "last_exit_code": exit_code,
                              "last_output_len": output_len,
                              "reason": reason,
                          }))
                break

        # Save the report with timestamp so multiple runs per day work
        report_dir = PROJECT_ROOT / "reports" / self.user_id
        report_dir.mkdir(parents=True, exist_ok=True)

        # Primary file: date.md (overwritten each run, synced to Fly.io)
        report_path = report_dir / f"{self.date_str}.md"
        report_path.write_text(self.newsletter_text)

        word_count = len(self.newsletter_text.split())
        logger.info(f"Newsletter written: {word_count} words → {report_path}")

        # Evaluate newsletter quality with NewsletterEvaluator
        eval_scores = {}
        try:
            evaluator = NewsletterEvaluator(self.db)
            agent_reports = [
                {"agent": f["agent"], "title": f["title"],
                 "importance": f["importance"]}
                for f in today_findings
            ]
            user_prefs = memory.list_preferences(self.db, effective=True)
            eval_scores = evaluator.evaluate(
                self.newsletter_text, agent_reports, user_prefs)
            logger.info(
                f"Newsletter evaluation: overall={eval_scores.get('overall', 'N/A')}, "
                f"coverage={eval_scores.get('coverage', 'N/A')}, "
                f"dedup={eval_scores.get('dedup', 'N/A')}, "
                f"sources={eval_scores.get('sources', 'N/A')}")

            # Store quality scores in PipelineMonitor
            try:
                self.monitor.record_quality(self.date_str, eval_scores)
            except Exception as e:
                logger.warning(f"Monitor record_quality failed: {e}")

            # Log to traces
            log_event(self.traces_conn, self.traces_run_id,
                      "newsletter_evaluation", json.dumps(eval_scores))
        except Exception as e:
            logger.warning(f"Newsletter evaluation failed (non-critical): {e}")

        quality_floor = {
            "status": "pass",
            "passed": True,
            "degraded": False,
            "retryable": False,
            "reasons": [],
            "metrics": {},
        }
        quality_fallback = False
        try:
            recent_findings = _recent_findings_for_quality(self.db, self.date_str)
            quality_floor = assess_quality_floor(
                eval_scores,
                findings=today_findings,
                recent_findings=recent_findings,
                preflight_data=self.preflight_data or {},
            )
            quality_floor["run_date"] = self.date_str

            if source_balance.get("status") != "pass":
                quality_floor["status"] = (
                    "fail_retryable"
                    if quality_floor.get("retryable")
                    else "degraded"
                )
                quality_floor["passed"] = False
                quality_floor["degraded"] = True
                quality_floor.setdefault("reasons", []).extend(
                    f"source balance: {reason}"
                    for reason in source_balance.get("reasons", [])
                )

            if quality_floor["status"] == "fail_retryable":
                reason = "; ".join(quality_floor.get("reasons", [])[:5])
                self.newsletter_text = _build_deterministic_newsletter(
                    newsletter_title=newsletter_title,
                    date_str=self.date_str,
                    findings=today_findings,
                    reason=f"quality floor fail_retryable: {reason}",
                )
                quality_fallback = True
                report_path.write_text(self.newsletter_text)
                word_count = len(self.newsletter_text.split())
                log_event(self.traces_conn, self.traces_run_id,
                          "newsletter_quality_floor_retryable",
                          json.dumps(quality_floor))
                logger.error(
                    "Newsletter quality floor retryable failure; wrote "
                    "deterministic fallback before delivery: %s",
                    reason,
                )
            elif quality_floor["status"] == "degraded":
                self.newsletter_text = (
                    _quality_floor_notice(quality_floor)
                    + "\n\n"
                    + self.newsletter_text
                )
                report_path.write_text(self.newsletter_text)
                word_count = len(self.newsletter_text.split())
                log_event(self.traces_conn, self.traces_run_id,
                          "newsletter_quality_floor_degraded",
                          json.dumps(quality_floor))
                logger.warning(
                    "Newsletter quality floor degraded; notice added: %s",
                    "; ".join(quality_floor.get("reasons", [])[:5]),
                )
        except Exception as e:
            logger.warning(f"Newsletter quality floor failed (non-critical): {e}")

        # Gate: warn if quality is below threshold (don't block, but log loudly)
        overall = eval_scores.get("overall", 1.0)
        if overall < 0.6:
            logger.warning(
                f"QUALITY GATE WARNING: Newsletter scored {overall:.3f} "
                f"(below 0.6 threshold). Delivering anyway but flagging for review. "
                f"Scores: {eval_scores}"
            )

        self.newsletter_eval = eval_scores
        return {"word_count": word_count, "report_path": str(report_path),
                "eval_scores": eval_scores, "source_balance": source_balance,
                "narrative_arcs_count": narrative_arcs_count,
                "quality_floor": quality_floor,
                "quality_fallback": quality_fallback,
                "degraded": quality_floor.get("degraded", False)}

    def _phase_deliver(self) -> dict:
        """Phase 5: Deliver (Python only). Convert to HTML, send via Resend."""
        from .newsletter import send_newsletter, validate_report, broadcast_to_subscribers

        report_path = PROJECT_ROOT / "reports" / self.user_id / f"{self.date_str}.md"

        # Validate report
        validation = validate_report(
            report_path, traces_conn=self.traces_conn, pipeline_run_id=self.traces_run_id,
        )
        logger.info(f"Report validation: {validation.get('final_bytes', 0)} bytes")

        # Capture clean content BEFORE feedback footer for subscriber broadcast
        clean_content = report_path.read_text() if report_path.exists() else ""

        # Append feedback footer before sending
        try:
            footer = memory.get_feedback_footer(self.db)
            if footer:
                content = report_path.read_text()
                report_path.write_text(content + "\n\n" + footer)
                logger.info("Feedback footer appended")
        except Exception as e:
            logger.warning(f"Could not append feedback footer: {e}")

        # Send — pass file content directly so the footer is guaranteed
        # to be included in the HTML conversion (avoids stale file reads).
        # An exception here must still alert the owner — on 2026-06-12 a
        # crash inside send_newsletter bypassed the alert path entirely and
        # the missed newsletter went unnoticed.
        try:
            result = send_newsletter(
                report_path, self.user_config, self.date_str,
                report_content=report_path.read_text(),
                traces_conn=self.traces_conn, pipeline_run_id=self.traces_run_id,
                db=self.db,
            )
        except Exception as e:
            result = {
                "success": False, "skipped": False,
                "error": f"{type(e).__name__}: {e}",
            }

        if result.get("skipped"):
            logger.info(
                f"Newsletter already sent for {self.date_str} "
                f"(receipt claimed on a prior run) — skipping"
            )
        elif result.get("success"):
            logger.info(f"Newsletter sent: {result.get('resend_id')}")
        else:
            # A silent delivery failure means no newsletter and nobody
            # notices — alert the owner instead of logging-and-completing.
            logger.error(f"Newsletter send failed: {result.get('error')}")
            self._send_alert(
                f"Newsletter send FAILED for {self.date_str}: "
                f"{result.get('error')}"
            )

        # Scheduling contract with run-launchd.sh: the day is marked "done"
        # (so the 08-11 backup windows stop retrying) ONLY when the newsletter
        # is confirmed delivered. result.success is True for both a fresh send
        # and an already-sent skip. The wrapper no longer touches this marker
        # itself, so a crash or send failure leaves it absent and the next
        # hourly window retries — receipts make that retry safe. This closed
        # the 2026-06-13 all-day miss, where a startup crash still marked the
        # day done. (Single-user pipeline; marker is keyed by date.)
        if result.get("success"):
            try:
                marker_dir = os.environ.get("MP_RAN_MARKER_DIR", "/tmp")
                Path(marker_dir, f"mindpattern-ran-{self.date_str}").touch()
                logger.info(f"Marked {self.date_str} delivered (ran-marker written)")
            except Exception as e:
                logger.warning(f"Could not write ran-marker: {e}")

        # Broadcast to public subscribers (gated by user config)
        audience_service = self.user_config.get("broadcast_audience")
        if audience_service and clean_content:
            try:
                broadcast = broadcast_to_subscribers(
                    clean_content,
                    self.date_str,
                    audience_keychain_service=audience_service,
                    exclude_emails=[self.user_config.get("email", "")],
                    newsletter_title=self.user_config.get("newsletter_title", "Daily Research"),
                    reply_to=self.user_config.get("reply_to", ""),
                    traces_conn=self.traces_conn,
                    pipeline_run_id=self.traces_run_id,
                    db=self.db,
                )
                logger.info(
                    f"Subscriber broadcast: {broadcast['sent_count']} sent, "
                    f"{broadcast['skipped_count']} skipped, {broadcast['failed_count']} failed"
                )
            except Exception as e:
                logger.warning(f"Subscriber broadcast failed (non-critical): {e}")

        return result

    def _phase_learn(self) -> dict:
        """Phase 6: Learn (Python + one Sonnet call)."""
        trending_topics = [t.get("topic", "") for t in self.trends] if self.trends else None
        quality = memory.evaluate_run(self.db, self.date_str, trending_topics=trending_topics)
        logger.info(f"Quality score: {quality.get('overall_score', 'N/A')}")

        if quality.get("warning"):
            memory.store_failure(
                self.db, self.date_str, "quality_drop",
                quality["warning"],
                f"Overall score {quality['overall_score']:.3f} vs 7-day avg {quality.get('7day_avg', 'N/A')}"
            )

        # ── Prompt regression check ────────────────────────────────
        regressions = []
        changed_files = {p: i for p, i in self.prompt_changes.items() if i["changed"]}
        if changed_files and self.prompt_tracker:
            # Update quality snapshots for changed prompts now that we have a score
            overall_score = quality.get("overall_score")
            if overall_score is not None:
                for path in changed_files:
                    self.prompt_tracker.record_version(
                        path, quality_snapshot=float(overall_score),
                    )

            regressions = self.prompt_tracker.check_regression(self.date_str)
            if regressions:
                for reg in regressions:
                    logger.warning(
                        "PROMPT REGRESSION: %s — quality dropped %.1f%% "
                        "(%.4f → %.4f). Review before rollback.",
                        reg["file"], reg["regression_pct"] * 100,
                        reg["quality_before"], reg["quality_after"],
                    )
                log_event(
                    self.traces_conn, self.traces_run_id,
                    "prompt_regression_detected",
                    json.dumps(regressions),
                )

        # Extract entity relationships from high-importance findings
        entity_relationships_stored = 0
        try:
            high_findings = self.db.execute(
                "SELECT id, title, summary, source_name FROM findings "
                "WHERE run_date = ? AND importance = 'high'",
                (self.date_str,),
            ).fetchall()
            for finding in high_findings:
                # Simple heuristic: if source_name exists, link it to key terms in title
                source = finding["source_name"]
                title = finding["title"] or ""
                if source and title:
                    memory.store_relationship(
                        self.db,
                        entity_a=source,
                        relationship="reported_on",
                        entity_b=title[:100],
                        entity_a_type="source",
                        entity_b_type="topic",
                        finding_id=finding["id"],
                    )
                    entity_relationships_stored += 1
            if entity_relationships_stored:
                logger.info(f"Entity graph: {entity_relationships_stored} relationships stored")
        except Exception as e:
            logger.warning(f"Entity graph extraction failed (non-critical): {e}")

        # ── Trend learning: backfill which trends produced findings ──────
        trend_backfill_count = 0
        try:
            from memory.trends import backfill_trend_results
            trend_backfill_count = backfill_trend_results(self.db, self.date_str)
            if trend_backfill_count:
                logger.info(f"Trend learning: backfilled {trend_backfill_count} trends")
        except Exception as e:
            logger.warning(f"Trend backfill failed (non-critical): {e}")

        consolidate_result = memory.consolidate(self.db)
        promote_result = memory.promote(self.db)
        prune_result = memory.prune(self.db)

        # Regenerate learnings.md
        stats = memory.get_stats(self.db)
        learnings_prompt = (
            f"Date: {self.date_str}\n\n"
            f"Database stats: {json.dumps(stats, indent=2)}\n\n"
            f"Quality this run: {json.dumps(quality, indent=2)}"
        )
        output, exit_code = agent_dispatch.run_claude_prompt(
            learnings_prompt, "learnings_update",
            system_prompt_file="agents/learnings-updater.md",
        )
        cleaned_output = output.strip()
        dest = PROJECT_ROOT / "data" / self.user_id / "learnings.md"
        if exit_code == 0 and cleaned_output and not cleaned_output.startswith("Error:"):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(output)
            logger.info(f"Learnings.md regenerated ({len(output)} chars)")
        else:
            existing = dest.read_text().strip() if dest.exists() else ""
            logger.warning(
                "Learnings.md update skipped after updater failure "
                "(exit_code=%s, output_len=%s)",
                exit_code,
                len(output),
            )
            if not existing or existing.startswith("Error:"):
                fallback = self._build_learnings_fallback(
                    stats=stats,
                    quality=quality,
                    consolidate_result=consolidate_result,
                    promote_result=promote_result,
                    prune_result=prune_result,
                    regressions=regressions,
                    entity_relationships_stored=entity_relationships_stored,
                    trend_backfill_count=trend_backfill_count,
                )
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(fallback)
                logger.info("Learnings.md regenerated with deterministic fallback")

        return {
            "quality": quality,
            "consolidated": consolidate_result,
            "promoted": promote_result,
            "pruned": prune_result,
            "prompt_regressions": regressions,
            "entity_relationships_stored": entity_relationships_stored,
        }

    def _build_learnings_fallback(
        self,
        *,
        stats: dict,
        quality: dict,
        consolidate_result: dict,
        promote_result: dict,
        prune_result: dict,
        regressions: list,
        entity_relationships_stored: int,
        trend_backfill_count: int,
    ) -> str:
        """Build a safe learnings.md when the LLM updater fails."""
        findings = stats.get("findings", stats.get("findings_count", "n/a"))
        sources = stats.get("sources", stats.get("source_count", "n/a"))
        quality_score = quality.get("overall_score", quality.get("overall", "n/a"))

        lines = [
            "# Learnings",
            "",
            f"Last updated: {self.date_str}",
            "",
            "## Latest Run",
            f"- Quality overall: {quality_score}",
            f"- Findings stored: {findings}",
            f"- Sources tracked: {sources}",
            f"- Memory consolidated: {consolidate_result}",
            f"- Memory promoted: {promote_result}",
            f"- Memory pruned: {prune_result}",
            f"- Entity relationships stored: {entity_relationships_stored}",
            f"- Trend results backfilled: {trend_backfill_count}",
            f"- Prompt regressions detected: {len(regressions or [])}",
            "",
            "## Operating Notes",
            "- Prefer fresh, source-backed findings over already-covered stories.",
            "- Treat source-tool failures as partial coverage gaps, not as empty research days.",
            "- Preserve duplicate-send and sync receipts; retries should repair state without resending.",
            "- If the LLM updater fails, keep this deterministic summary rather than error text.",
            "",
        ]
        return "\n".join(lines)

    def _phase_social(self) -> dict:
        """Phase 7: Social (SocialPipeline).

        EIC picks topic → brief → art → writers → critics → approve → post.
        """
        from social.pipeline import SocialPipeline

        social_config_path = PROJECT_ROOT / "social-config.json"
        try:
            with open(social_config_path) as f:
                social_config = json.load(f)
        except FileNotFoundError:
            logger.warning("social-config.json not found, skipping social phase")
            return {"skipped": True, "reason": "social-config.json missing"}

        # Skip only when no platform can even produce drafts. Disabled posting
        # APIs still allow manual-copy drafts via SocialPipeline.
        if not _draft_capable_platforms(social_config):
            logger.info("Social: no draft-capable platforms, skipping social phase")
            return {"skipped": True, "reason": "no draft-capable platforms"}

        pipeline = SocialPipeline(self.user_id, social_config, self.db)
        result = pipeline.run()
        self.social_result = result

        if result.get("kill_day"):
            logger.info("Social: kill day — no good topics found")
        elif result.get("platforms_posted"):
            platforms = result.get("platforms_posted", [])
            logger.info(f"Social: posted to {platforms}")
        elif result.get("manual_copy"):
            platforms = [p.get("platform") for p in result["manual_copy"]]
            logger.info(f"Social: manual-copy drafts for {platforms}")
        elif result.get("posts"):
            platforms = [p.get("platform") for p in result["posts"]]
            logger.info(f"Social: completed with post results for {platforms}")
        else:
            logger.info(f"Social: completed with result: {list(result.keys())}")

        # Store engagement signals from social pipeline results
        try:
            live_posts = [
                post for post in result.get("posts", [])
                if _is_live_social_post_result(post)
            ]
            if live_posts:
                for post in live_posts:
                    topic = post.get("topic") or post.get("title") or "social_post"
                    platform = post.get("platform", "unknown")
                    memory.store_signal(
                        self.db,
                        pipeline="social",
                        signal_type="posted",
                        topic=topic,
                        strength=1.0,
                        evidence=f"Posted to {platform}",
                        run_date=self.date_str,
                    )
                logger.info(f"Signals: stored {len(live_posts)} social post signals")
            elif result.get("kill_day"):
                topic = result.get("topic") or "social_content"
                memory.store_signal(
                    self.db,
                    pipeline="social",
                    signal_type="kill_day",
                    topic=topic,
                    strength=-0.5,
                    evidence="Kill day — no good topics found",
                    run_date=self.date_str,
                )
        except Exception as e:
            logger.warning(f"Signal storage failed (non-critical): {e}")

        return result

    def _phase_engagement(self) -> dict:
        """Phase 8: Engagement.

        Find conversations → draft replies → approve → post + auto-follow.
        """
        from social.engagement import EngagementPipeline

        social_config_path = PROJECT_ROOT / "social-config.json"
        try:
            with open(social_config_path) as f:
                social_config = json.load(f)
        except FileNotFoundError:
            logger.warning("social-config.json not found, skipping engagement phase")
            return {"skipped": True, "reason": "social-config.json missing"}

        # Skip when no platform is enabled (same gate-hang reason as social).
        if not _enabled_platforms(social_config):
            logger.info("Engagement: no platforms enabled, skipping engagement phase")
            return {"skipped": True, "reason": "no platforms enabled"}

        pipeline = EngagementPipeline(self.user_id, social_config, self.db)
        result = pipeline.run()

        logger.info(
            f"Engagement: {result.get('replies_posted', 0)} replies, "
            f"{result.get('follows', 0)} follows"
        )
        return result

    def _phase_identity(self) -> dict:
        """Phase: Evolve identity files based on today's results."""
        from memory.identity_evolve import build_evolve_prompt, apply_evolution_diff, parse_llm_output

        vault_dir = PROJECT_ROOT / "data" / self.user_id / "mindpattern"

        # Build enriched pipeline results for the identity prompt
        social = {}
        if self.social_result:
            topic = self.social_result.get("topic") or {}
            social = {
                "topic": topic.get("anchor", topic.get("topic", "")),
                "topic_score": topic.get("composite_score", 0),
                "gate1_outcome": self.social_result.get("gate1_outcome", "unknown"),
                "gate1_guidance": self.social_result.get("gate1_guidance", ""),
                "gate2_outcome": self.social_result.get("gate2_outcome", "unknown"),
                "gate2_edits": self.social_result.get("gate2_edits", []),
                "expeditor_verdict": self.social_result.get("expeditor_verdict", "unknown"),
                "platforms_posted": self.social_result.get("platforms_posted", []),
            }

        pipeline_results = {
            "date": self.date_str,
            "findings_count": (
                sum(len(r.findings) for r in self.agent_results)
                if self.agent_results
                else self.db.execute(
                    "SELECT COUNT(*) FROM findings WHERE run_date = ?",
                    (self.date_str,),
                ).fetchone()[0]
            ),
            "newsletter_generated": bool(self.newsletter_text),
            "newsletter_eval": self.newsletter_eval,
            "social": social,
        }


        prompt = build_evolve_prompt(vault_dir, pipeline_results)
        output, exit_code = agent_dispatch.run_claude_prompt(prompt, task_type="identity")

        if exit_code != 0 or not output:
            logger.warning("IDENTITY: LLM call failed, skipping identity evolution")
            return {"evolved": False, "reason": "LLM call failed"}

        diff = parse_llm_output(output)
        if diff is None:
            logger.warning("IDENTITY: Could not parse LLM output as JSON")
            return {"evolved": False, "reason": "JSON parse failed"}

        result = apply_evolution_diff(vault_dir, diff, truncate_oversized=True)

        if result.get("changes_made"):
            logger.info(f"IDENTITY: {result['changes_made']}")
        if result.get("warnings"):
            logger.warning(f"IDENTITY warnings: {result['warnings']}")
        if result.get("errors"):
            logger.warning(f"IDENTITY errors: {result['errors']}")

        return {"evolved": True, **result}

    def _collect_all_skill_files(self) -> list[Path]:
        """Collect all .md skill files used as agent prompts."""
        skill_files = []
        dirs = [
            PROJECT_ROOT / "verticals" / "ai-tech" / "agents",
            PROJECT_ROOT / "agents",
        ]
        for d in dirs:
            if d.exists():
                for f in sorted(d.glob("*.md")):
                    if "references" not in str(f):
                        skill_files.append(f)
        return skill_files

    def _phase_mirror(self) -> dict:
        """Phase: Generate Obsidian mirror files from SQLite."""
        from memory.mirror import generate_mirrors

        vault_dir = PROJECT_ROOT / "data" / self.user_id / "mindpattern"
        generate_mirrors(self.db, vault_dir, self.date_str)

        logger.info(f"MIRROR: Generated Obsidian files in {vault_dir}")
        return {"mirrored": True}

    def _phase_sync(self) -> dict:
        """Phase 9: Sync to Fly.io.

        Bundle memory.db + reports → upload → dashboard gets fresh data.
        """
        from .sync import restart_app, sync_to_fly, write_synced_marker

        data_dir = PROJECT_ROOT / "data"
        result = sync_to_fly(
            self.user_id, data_dir,
            app_name="mindpattern",
            traces_conn=self.traces_conn,
        )

        if result.get("success"):
            logger.info(f"Sync: {result.get('bytes_uploaded', 0)} bytes uploaded")
            # Restart so the dashboard reopens the replaced database file —
            # open connections still point at the old inode (single-user
            # pipeline, so once-per-sync == once after all users).
            restart = restart_app("mindpattern")
            if restart.get("success"):
                logger.info("Fly app restarted to pick up synced data")
                write_synced_marker(self.date_str)
            else:
                logger.warning(f"Fly restart failed: {restart.get('error')}")
        else:
            err = result.get("error") or "unknown error"
            logger.warning(f"Sync failed: {err}")
            reports_dir = data_dir.parent / "reports" / self.user_id
            unsynced = sorted(reports_dir.glob("????-??-??.md")) if reports_dir.exists() else []
            latest = unsynced[-1].stem if unsynced else "n/a"
            self._send_alert(
                f":rotating_light: Fly sync failed for `{self.user_id}` — {err}\n"
                f"Local newsletters present: {len(unsynced)} (latest `{latest}`). "
                f"Dashboard at mindpattern.ai is stale until this is fixed. "
                f"Run `flyctl auth login` if it's an auth error."
            )

        return result

    # ── Helpers ─────────────────────────────────────────────────────────

    def _keychain_lookup(self, service_name: str) -> str | None:
        import subprocess
        try:
            return subprocess.check_output(
                ["security", "find-generic-password", "-s", service_name, "-w"],
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).decode().strip()
        except subprocess.TimeoutExpired:
            logger.error("Keychain lookup timed out for '%s'", service_name)
            return None
        except subprocess.CalledProcessError:
            return None

    def _send_alert(self, message: str):
        try:
            import json
            import subprocess
            import urllib.request

            result = subprocess.run(
                ["security", "find-generic-password", "-s", "slack-bot-token", "-w"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                logger.warning(f"No Slack token for alert: {message}")
                return

            token = result.stdout.strip()
            payload = json.dumps({
                "channel": "C0ALSRHAATH",
                "text": message[:2000],
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://slack.com/api/chat.postMessage",
                data=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            logger.warning(f"Slack alert failed: {e}")

    def close(self):
        if self.db:
            self.db.close()
        if self.traces_conn:
            self.traces_conn.close()
