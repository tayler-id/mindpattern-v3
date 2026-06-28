"""Narrative arc extraction for multi-day story patterns.

Feature 17 is enrichment-only: this module produces source-backed arc artifacts
for synthesis pass 2 and public API use. It does not select newsletter stories.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from orchestrator.media_contracts import (
    EvidenceReference,
    normalize_artifact_slug,
    redact_sensitive_text,
    validate_run_date,
)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_REPORTS_ROOT = PROJECT_ROOT / "reports"

_SAFE_USER_RE = re.compile(r"^[a-z0-9_-]+$")
_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#._-]{2,}")
_STOPWORDS = {
    "about", "after", "again", "also", "and", "are",
    "around", "become", "becomes", "being", "from", "into", "that",
    "their", "there", "this", "those", "through", "update", "using",
    "with", "work", "workflow", "workflows", "the", "for", "new", "now",
}


def build_narrative_arcs(
    findings: list[dict[str, Any]],
    *,
    date: str,
    artifact_root: Path | None = None,
    user: str = "ramsay",
    window_days: int = 30,
    write_artifact: bool = True,
) -> dict[str, Any]:
    """Build deterministic narrative arcs from recent findings.

    A valid arc needs at least three evidence items across at least two dates.
    Stale arcs can be returned for audit, but synthesis should only inject
    active/emerging arcs with fresh evidence.
    """
    target_date = _parse_date(date)
    root = artifact_root or DEFAULT_REPORTS_ROOT
    if not _SAFE_USER_RE.fullmatch(user or ""):
        raise ValueError("user must be a safe path segment")

    candidates = [
        _prepare_finding(f)
        for f in findings
        if _is_recent_enough(f, target_date, window_days)
    ]
    clusters = _cluster_findings(candidates)

    arcs: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for cluster in clusters:
        arc = _cluster_to_arc(cluster, target_date)
        if arc is None:
            rejected.append(_rejection_for_cluster(cluster))
            continue
        arcs.append(arc)

    arcs.sort(
        key=lambda arc: (
            -arc["scores"]["confidence"],
            -arc["scores"]["freshness"],
            arc["id"],
        )
    )
    payload = {
        "date": validate_run_date(date),
        "user": user,
        "arcs": arcs,
        "rejected": sorted(rejected, key=lambda item: item["theme"]),
        "summary": {
            "accepted_count": len(arcs),
            "rejected_count": len(rejected),
            "input_count": len(findings),
            "candidate_count": len(candidates),
        },
    }

    if write_artifact:
        artifact_path = narrative_arcs_artifact_path(
            date=date,
            user=user,
            reports_root=root,
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        payload["artifact_path"] = str(artifact_path)

    return payload


def narrative_arcs_artifact_path(
    *,
    date: str,
    user: str = "ramsay",
    reports_root: Path | None = None,
) -> Path:
    """Return the safe artifact path for a day's narrative arcs."""
    if not _SAFE_USER_RE.fullmatch(user or ""):
        raise ValueError("user must be a safe path segment")
    date = validate_run_date(date)
    root = (reports_root or DEFAULT_REPORTS_ROOT).resolve()
    path = (root / user / "arcs" / f"{date}.json").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("arc artifact path escapes reports root") from exc
    return path


def load_narrative_arcs(
    *,
    date: str,
    user: str = "ramsay",
    reports_root: Path | None = None,
    limit: int | None = None,
    statuses: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Load sanitized narrative arcs from the daily artifact."""
    path = narrative_arcs_artifact_path(date=date, user=user, reports_root=reports_root)
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    arcs = list(payload.get("arcs") or [])
    if statuses:
        arcs = [arc for arc in arcs if arc.get("status") in statuses]
    if limit is not None:
        arcs = arcs[: max(0, int(limit))]
    return arcs


def format_arcs_for_synthesis(arcs: list[dict[str, Any]], *, limit: int = 5) -> str:
    """Format active arcs as pass-2 narrative context."""
    usable = [
        arc for arc in arcs
        if arc.get("status") in {"active", "emerging"} and arc.get("evidence")
    ][:limit]
    if not usable:
        return ""
    lines = ["## Narrative Arc Context", "Use as context only. Do not change the selected story set."]
    for arc in usable:
        lines.append(
            f"- {arc['title']} ({arc['status']}, confidence "
            f"{arc['scores']['confidence']:.2f}): {arc['summary']}"
        )
        evidence_bits = []
        for item in arc.get("evidence", [])[:3]:
            label = item.get("source_name") or item.get("agent") or "source"
            evidence_bits.append(f"{item.get('run_date')}: {label} #{item.get('finding_id', '?')}")
        if evidence_bits:
            lines.append(f"  Evidence: {'; '.join(evidence_bits)}")
    return "\n".join(lines).strip()


def _parse_date(value: str) -> datetime:
    return datetime.strptime(validate_run_date(value), "%Y-%m-%d")


def _is_recent_enough(finding: dict[str, Any], target_date: datetime, window_days: int) -> bool:
    try:
        run_date = _parse_date(str(finding.get("run_date", "")))
    except ValueError:
        return False
    delta = (target_date - run_date).days
    return 0 <= delta <= window_days


def _prepare_finding(finding: dict[str, Any]) -> dict[str, Any]:
    tokens = _tokens(f"{finding.get('title', '')} {finding.get('summary', '')}")
    return {
        **finding,
        "_tokens": tokens,
        "_domain": _domain(finding.get("source_url", "")) or str(finding.get("source_name", "")).lower(),
    }


def _cluster_findings(findings: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for finding in sorted(
        findings,
        key=lambda item: (
            str(item.get("run_date", "")),
            str(item.get("title", "")),
            str(item.get("id", "")),
        ),
    ):
        best_cluster = None
        best_score = 0.0
        for cluster in clusters:
            score = max(_similarity(finding["_tokens"], other["_tokens"]) for other in cluster)
            if score > best_score:
                best_score = score
                best_cluster = cluster
        if best_cluster is not None and best_score >= 0.24:
            best_cluster.append(finding)
        else:
            clusters.append([finding])
    return clusters


def _cluster_to_arc(cluster: list[dict[str, Any]], target_date: datetime) -> dict[str, Any] | None:
    evidence_count = len(cluster)
    run_dates = sorted({str(item.get("run_date", "")) for item in cluster})
    if evidence_count < 3 or len(run_dates) < 2:
        return None

    source_domains = sorted({str(item.get("_domain", "")) for item in cluster if item.get("_domain")})
    agents = sorted({str(item.get("agent", "")) for item in cluster if item.get("agent")})
    if len(source_domains) < 2 and len(agents) < 2:
        return None

    title = _arc_title(cluster)
    arc_id = _stable_arc_id(title, cluster)
    last_seen = max(_parse_date(date) for date in run_dates)
    days_since_seen = (target_date - last_seen).days
    status = _arc_status(days_since_seen, evidence_count, len(run_dates))
    scores = _scores(cluster, target_date, len(source_domains), len(run_dates))

    evidence = [
        EvidenceReference.from_finding(item).to_public_dict()
        for item in sorted(cluster, key=lambda i: (i["run_date"], str(i.get("id", ""))))
    ]
    return {
        "id": arc_id,
        "title": title,
        "summary": _arc_summary(title, cluster),
        "status": status,
        "first_seen": run_dates[0],
        "last_seen": run_dates[-1],
        "evidence_count": evidence_count,
        "date_count": len(run_dates),
        "source_domain_count": len(source_domains),
        "agent_count": len(agents),
        "scores": scores,
        "evidence": evidence,
    }


def _rejection_for_cluster(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    dates = sorted({str(item.get("run_date", "")) for item in cluster})
    domains = sorted({str(item.get("_domain", "")) for item in cluster if item.get("_domain")})
    agents = sorted({str(item.get("agent", "")) for item in cluster if item.get("agent")})
    if len(cluster) < 3:
        reason = "too_few_evidence_items"
    elif len(dates) < 2:
        reason = "single_day_only"
    elif len(domains) < 2 and len(agents) < 2:
        reason = "weak_source_diversity"
    else:
        reason = "below_threshold"
    return {
        "theme": _arc_title(cluster),
        "reason": reason,
        "evidence_count": len(cluster),
        "date_count": len(dates),
    }


def _tokens(text: str) -> set[str]:
    tokens = set()
    for raw in _TOKEN_RE.findall(text.lower()):
        token = raw.strip("._-")
        if len(token) < 4 or token in _STOPWORDS:
            continue
        tokens.add(_stem(token))
    return tokens


def _stem(token: str) -> str:
    aliases = {
        "ide": "ide",
        "ides": "ide",
        "code": "code",
        "coding": "code",
        "coded": "code",
        "agentic": "agent",
        "agents": "agent",
    }
    if token in aliases:
        return aliases[token]
    for suffix in ("ing", "ers", "ies", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    if overlap >= 2:
        return overlap / math.sqrt(len(a) * len(b))
    return overlap / len(a | b)


def _arc_title(cluster: list[dict[str, Any]]) -> str:
    token_counts = Counter()
    for item in cluster:
        token_counts.update(item["_tokens"])
    chosen = [
        token for token, _count in token_counts.most_common(5)
        if token not in {"duplicate", "coverage", "summary"}
    ][:4]
    if chosen:
        return " ".join(chosen).title()
    return redact_sensitive_text(str(cluster[0].get("title", "Narrative arc")))[:120]


def _arc_summary(title: str, cluster: list[dict[str, Any]]) -> str:
    dates = sorted({str(item.get("run_date", "")) for item in cluster})
    sources = sorted({str(item.get("source_name", "")) for item in cluster if item.get("source_name")})
    source_text = ", ".join(sources[:3]) if sources else "multiple sources"
    return (
        f"{title} appears across {len(cluster)} findings from {len(dates)} dates "
        f"and {source_text}."
    )


def _stable_arc_id(title: str, cluster: list[dict[str, Any]]) -> str:
    canonical = normalize_artifact_slug(title)
    evidence_ids = sorted(str(item.get("id", "")) for item in cluster if item.get("id") is not None)
    digest = hashlib.sha1(("|".join([canonical, *evidence_ids])).encode()).hexdigest()[:8]
    return f"{canonical}-{digest}"


def _arc_status(days_since_seen: int, evidence_count: int, date_count: int) -> str:
    if days_since_seen > 7:
        return "stale"
    if evidence_count >= 5 or date_count >= 3:
        return "active"
    return "emerging"


def _scores(
    cluster: list[dict[str, Any]],
    target_date: datetime,
    source_count: int,
    date_count: int,
) -> dict[str, float]:
    last_seen = max(_parse_date(str(item["run_date"])) for item in cluster)
    days_since_seen = (target_date - last_seen).days
    recurrence = min(1.0, len(cluster) / 6)
    velocity = min(1.0, date_count / 4)
    source_diversity = min(1.0, source_count / 4)
    freshness = 0.0 if days_since_seen > 7 else max(0.0, 1 - (days_since_seen / 7))
    confidence = round((recurrence + velocity + source_diversity + freshness) / 4, 3)
    return {
        "recurrence": round(recurrence, 3),
        "velocity": round(velocity, 3),
        "source_diversity": round(source_diversity, 3),
        "freshness": round(freshness, 3),
        "confidence": confidence,
    }


def _domain(url: Any) -> str:
    parsed = urlparse(str(url or ""))
    return parsed.netloc.lower().removeprefix("www.")
