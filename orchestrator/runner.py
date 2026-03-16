"""Main pipeline runner — deterministic state machine.

Python controls the phase sequence. Each phase is either a focused claude -p call
or a Python-only step. The LLM never decides what phase comes next.
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import memory
from . import agents as agent_dispatch
from .checkpoint import Checkpoint
from .evaluator import NewsletterEvaluator
from .observability import PipelineMonitor
from .pipeline import Phase, PipelineRun, CRITICAL_PHASES
from .prompt_tracker import PromptTracker
from .traces_db import (
    get_db as get_traces_db,
    create_pipeline_run,
    complete_pipeline_run,
    log_event,
    create_phase as traces_create_phase,
    complete_phase as traces_complete_phase,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


class ResearchPipeline:
    """Orchestrates the full research pipeline for a single user."""

    def __init__(self, user_id: str, date_str: str | None = None):
        self.user_id = user_id
        self.date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        self.user_config = agent_dispatch.load_user_config(user_id)
        self.global_config = agent_dispatch.load_global_config()
        self.db = memory.get_db(user_id=user_id)
        self.trends: list[dict] = []
        self.agent_results: list = []
        self.newsletter_text: str = ""
        self.newsletter_eval: dict = {}
        self.social_result: dict = {}

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
            metadata=json.dumps({"user_id": user_id, "date": self.date_str}),
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
                    self.checkpoint.save(self.pipeline.run_id, phase, result)
                else:
                    logger.warning(f"No handler for phase {phase.value}, skipping")
                    self.pipeline.complete_phase(phase)
                    self.checkpoint.save(self.pipeline.run_id, phase)
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
                    self.checkpoint.save(self.pipeline.run_id, phase, {"error": str(e)})

        # Mark completed
        self.pipeline.transition(Phase.COMPLETED)
        self.checkpoint.save(self.pipeline.run_id, Phase.COMPLETED)

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

    def _get_phase_handler(self, phase: Phase):
        """Map phases to their handler methods."""
        return {
            Phase.INIT: self._phase_init,
            Phase.TREND_SCAN: self._phase_trend_scan,
            Phase.RESEARCH: self._phase_research,
            Phase.SYNTHESIS: self._phase_synthesis,
            Phase.DELIVER: self._phase_deliver,
            Phase.LEARN: self._phase_learn,
            Phase.SOCIAL: self._phase_social,
            Phase.ENGAGEMENT: self._phase_engagement,
            Phase.EVOLVE: self._phase_evolve,
            Phase.MIRROR: self._phase_mirror,
            Phase.SYNC: self._phase_sync,
        }.get(phase)

    # ── Phase handlers ─────────────────────────────────────────────────

    def _phase_init(self) -> dict:
        """Phase 1: Init (Python only, no LLM)."""
        prefs = memory.list_preferences(self.db, email=self.user_config.get("email"), effective=True)
        logger.info(f"Loaded {len(prefs)} preferences")

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

    def _phase_trend_scan(self) -> dict:
        """Phase 2: Trend Scan (Haiku).

        Skippable — if it fails, research agents run without trends.
        """
        # Instead of using a template with {url_summaries} that we don't have,
        # ask the LLM to search for trends directly
        prompt = (
            f"Today is {self.date_str}. Search the web for the latest AI and tech news. "
            f"Identify 5-8 trending topics relevant to developers building with AI.\n\n"
            f"Focus on: AI agents, vibe coding, developer tools, ML infrastructure, AI security.\n"
            f"Ignore: funding rounds, hiring, stock prices.\n\n"
            f"Output ONLY a valid JSON array. Each element: "
            f'{{\"topic\": \"string\", \"evidence\": \"string\", \"relevance_score\": 0.0-1.0}}\n\n'
            f"No markdown fences. No explanation. Just the JSON array."
        )

        output, exit_code = agent_dispatch.run_claude_prompt(
            prompt, "trend_scan",
            allowed_tools=["WebSearch", "WebFetch"],
        )

        if exit_code != 0 or not output.strip():
            logger.warning("Trend scan returned no output")
            return {"trends": []}

        # Try to parse JSON from output (may have text around it)
        import re
        try:
            self.trends = json.loads(output.strip())
            if isinstance(self.trends, dict):
                self.trends = self.trends.get("topics", self.trends.get("trends", []))
        except json.JSONDecodeError:
            # Try to find JSON array in output
            match = re.search(r'\[[\s\S]*\]', output)
            if match:
                try:
                    self.trends = json.loads(match.group())
                except json.JSONDecodeError:
                    self.trends = []
            else:
                self.trends = []

        if not isinstance(self.trends, list):
            self.trends = []

        logger.info(f"Trend scan: {len(self.trends)} topics identified")
        return {"trends": self.trends}

    def _phase_research(self) -> dict:
        """Phase 3: Research (13x Sonnet, parallel)."""
        memory.clear_claims(self.db, self.date_str)

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

        current_claims = [c["topic_hash"] for c in memory.list_claims(self.db, self.date_str)]

        self.agent_results = agent_dispatch.dispatch_research_agents(
            user_id=self.user_id,
            date_str=self.date_str,
            context_fn=context_fn,
            trends=self.trends,
            claims=current_claims,
            max_workers=6,
        )

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

                    # Dedup: check if a very similar finding exists in the last 30 days
                    existing = memory.search_findings(
                        self.db, f"{title}. {summary}", limit=1, days=30,
                    )
                    if existing and existing[0].get("similarity", 0) > 0.85:
                        logger.debug(
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

        if total_stored == 0:
            raise RuntimeError("Zero findings stored — research phase failed")

        return {
            "agents_dispatched": len(self.agent_results),
            "agents_succeeded": successful,
            "findings_stored": total_stored,
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

        # Build summaries for pass 1 — full text, not truncated (we have 1M context)
        summaries = []
        for f in today_findings:
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

        # Pass 1: Story selection (inline prompt — no template placeholders to miss)
        pass1_prompt = (
            f"Select exactly 5 stories from these {len(summaries)} findings for today's newsletter.\n\n"
            f"Date: {self.date_str}\n\n"
            f"## User Preferences\n{pref_text}\n\n"
            f"## Trending Topics\n{trends_text}\n\n"
            f"## Findings\n" + "\n".join(summaries) + "\n\n"
            f"Selection criteria: cross-agent convergence, quantitative evidence, "
            f"builder relevance, source diversity.\n\n"
            f"Output ONLY a JSON array of 5 objects: "
            f'[{{"story_title": "...", "agent": "...", "section": "...", "reason": "..."}}]\n'
            f"No markdown fences. No explanation. Just JSON."
        )

        pass1_output, exit_code = agent_dispatch.run_claude_prompt(pass1_prompt, "synthesis_pass1")
        if exit_code != 0:
            logger.warning("Synthesis pass 1 failed, using all findings for pass 2")
            pass1_output = ""

        # Pass 2: Newsletter writing (inline prompt)
        full_findings = []
        for f in today_findings:
            source = f"[{f['source_name']}]({f['source_url']})" if f['source_url'] else f['source_name'] or 'unknown'
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

        pass2_prompt = (
            f"Write the \"{newsletter_title}\" newsletter for {self.date_str}.\n\n"
            f"You have {len(today_findings)} findings from {len(set(f['agent'] for f in today_findings))} agents.\n\n"
            f"## Story Selection\n{pass1_output or 'Use your judgment to select the Top 5.'}\n\n"
            f"## All Findings\n" + "\n".join(full_findings) + "\n\n"
            f"## User Preferences\n{pref_text}\n\n"
            f"{failure_text}\n\n"
            f"## Structure\n"
            f"1. Top 5 (200-400 words each with source links)\n"
            f"2. Per-section deep dives (skip empty sections)\n"
            f"3. Skills of the Day (10 actionable skills)\n\n"
            f"## Rules\n"
            f"- Every claim must have a source link [Source Name](url)\n"
            f"- No story in more than one section\n"
            f"- Voice: direct, technical, opinionated. Not corporate.\n"
            f"- MINIMUM 4000 words. Target 4500. The newsletter MUST be comprehensive.\n"
            f"- Write 200-400 words per Top 5 story. Write 100-200 words per deep dive finding.\n"
            f"- Include ALL sections that have findings. Do not skip sections to save space.\n\n"
            f"Output ONLY the newsletter markdown. Start with the title. No meta-commentary."
        )

        self.newsletter_text, exit_code = agent_dispatch.run_claude_prompt(pass2_prompt, "synthesis_pass2")

        if exit_code != 0 or not self.newsletter_text.strip():
            raise RuntimeError("Synthesis pass 2 failed — no newsletter generated")

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

        self.newsletter_eval = eval_scores
        return {"word_count": word_count, "report_path": str(report_path),
                "eval_scores": eval_scores}

    def _phase_deliver(self) -> dict:
        """Phase 5: Deliver (Python only). Convert to HTML, send via Resend."""
        from .newsletter import send_newsletter, validate_report

        report_path = PROJECT_ROOT / "reports" / self.user_id / f"{self.date_str}.md"

        # Validate report
        validation = validate_report(
            report_path, traces_conn=self.traces_conn, pipeline_run_id=self.traces_run_id,
        )
        logger.info(f"Report validation: {validation.get('final_bytes', 0)} bytes")

        # Append feedback footer before sending
        try:
            footer = memory.get_feedback_footer(self.db)
            if footer:
                content = report_path.read_text()
                report_path.write_text(content + "\n\n" + footer)
                logger.info("Feedback footer appended")
        except Exception as e:
            logger.warning(f"Could not append feedback footer: {e}")

        # Send
        result = send_newsletter(
            report_path, self.user_config, self.date_str,
            traces_conn=self.traces_conn, pipeline_run_id=self.traces_run_id,
        )

        if result.get("success"):
            logger.info(f"Newsletter sent: {result.get('resend_id')}")
        else:
            logger.warning(f"Newsletter send failed: {result.get('error')}")

        return result

    def _phase_learn(self) -> dict:
        """Phase 6: Learn (Python + one Sonnet call)."""
        trending_topics = ",".join(t.get("topic", "") for t in self.trends) if self.trends else None
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

        consolidate_result = memory.consolidate(self.db)
        promote_result = memory.promote(self.db)
        prune_result = memory.prune(self.db)

        # Regenerate learnings.md
        stats = memory.get_stats(self.db)
        learnings_prompt = (
            f"Regenerate the learnings.md summary for the mindpattern research agent.\n"
            f"Date: {self.date_str}\n\n"
            f"Database stats: {json.dumps(stats, indent=2)}\n\n"
            f"Quality this run: {json.dumps(quality, indent=2)}\n\n"
            f"Write a concise learnings summary covering:\n"
            f"- Key findings from recent runs\n"
            f"- Patterns observed\n"
            f"- Source insights\n"
            f"- Agent performance notes\n\n"
            f"Output ONLY the markdown. Keep to the 5 most recent runs."
        )
        output, _ = agent_dispatch.run_claude_prompt(learnings_prompt, "learnings_update")
        if output.strip():
            dest = PROJECT_ROOT / "data" / self.user_id / "learnings.md"
            dest.write_text(output)
            logger.info(f"Learnings.md regenerated ({len(output)} chars)")

        return {
            "quality": quality,
            "consolidated": consolidate_result,
            "promoted": promote_result,
            "pruned": prune_result,
            "prompt_regressions": regressions,
            "entity_relationships_stored": entity_relationships_stored,
        }

    def _phase_social(self) -> dict:
        """Phase 7: Social (SocialPipeline).

        EIC picks topic → brief → art → writers → critics → approve → post.
        """
        from social.pipeline import SocialPipeline

        social_config_path = PROJECT_ROOT / "social-config.json"
        with open(social_config_path) as f:
            social_config = json.load(f)

        pipeline = SocialPipeline(self.user_id, social_config, self.db)
        result = pipeline.run()
        self.social_result = result

        if result.get("kill_day"):
            logger.info("Social: kill day — no good topics found")
        elif result.get("posts"):
            platforms = [p.get("platform") for p in result["posts"]]
            logger.info(f"Social: posted to {platforms}")
        else:
            logger.info(f"Social: completed with result: {list(result.keys())}")

        # Store engagement signals from social pipeline results
        try:
            if result.get("posts"):
                for post in result["posts"]:
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
                logger.info(f"Signals: stored {len(result['posts'])} social post signals")
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
        with open(social_config_path) as f:
            social_config = json.load(f)

        pipeline = EngagementPipeline(self.user_id, social_config, self.db)
        result = pipeline.run()

        logger.info(
            f"Engagement: {result.get('replies_posted', 0)} replies, "
            f"{result.get('follows', 0)} follows"
        )
        return result

    def _phase_evolve(self) -> dict:
        """Phase: Evolve identity files based on today's results."""
        from memory.identity_evolve import build_evolve_prompt, apply_evolution_diff, parse_llm_output

        vault_dir = PROJECT_ROOT / "data" / self.user_id / "mindpattern"

        # Build enriched pipeline results for the evolve prompt
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
            "findings_count": len(self.agent_results) if self.agent_results else 0,
            "newsletter_generated": bool(self.newsletter_text),
            "newsletter_eval": self.newsletter_eval,
            "social": social,
        }

        prompt = build_evolve_prompt(vault_dir, pipeline_results)
        output, exit_code = agent_dispatch.run_claude_prompt(prompt, task_type="evolve")

        if exit_code != 0 or not output:
            logger.warning("EVOLVE: LLM call failed, skipping identity evolution")
            return {"evolved": False, "reason": "LLM call failed"}

        diff = parse_llm_output(output)
        if diff is None:
            logger.warning("EVOLVE: Could not parse LLM output as JSON")
            return {"evolved": False, "reason": "JSON parse failed"}

        result = apply_evolution_diff(vault_dir, diff)

        if result.get("changes_made"):
            logger.info(f"EVOLVE: {result['changes_made']}")
        if result.get("errors"):
            logger.warning(f"EVOLVE errors: {result['errors']}")

        return {"evolved": True, **result}

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
        from .sync import sync_to_fly

        data_dir = PROJECT_ROOT / "data"
        result = sync_to_fly(
            self.user_id, data_dir,
            app_name="mindpattern",
            traces_conn=self.traces_conn,
        )

        if result.get("success"):
            logger.info(f"Sync: {result.get('bytes_uploaded', 0)} bytes uploaded")
        else:
            logger.warning(f"Sync failed: {result.get('error')}")

        return result

    # ── Helpers ─────────────────────────────────────────────────────────

    def _keychain_lookup(self, service_name: str) -> str | None:
        import subprocess
        try:
            return subprocess.check_output(
                ["security", "find-generic-password", "-s", service_name, "-w"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except subprocess.CalledProcessError:
            return None

    def _send_alert(self, message: str):
        phone = self.user_config.get("phone")
        if not phone:
            logger.warning(f"No phone number for alerts: {message}")
            return
        try:
            import subprocess
            safe_msg = message.replace('"', '\\"')[:200]
            script = f'tell application "Messages" to send "{safe_msg}" to buddy "{phone}"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
        except Exception as e:
            logger.warning(f"iMessage alert failed: {e}")

    def close(self):
        if self.db:
            self.db.close()
        if self.traces_conn:
            self.traces_conn.close()
