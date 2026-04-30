import json

from backend.core import app, db, _to_iso, _utcnow
from backend.models import AnalysisJob, AnalysisResult


def log_event(event, level="info", **fields):
    payload = {
        "timestamp": _to_iso(_utcnow()),
        "event": event,
        **fields,
    }
    log_method = getattr(app.logger, level, app.logger.info)
    log_method(json.dumps(payload, default=str, separators=(",", ":")))


def _job_stats_snapshot(now=None):
    now = now or _utcnow()
    status_counts_rows = (
        db.session.query(AnalysisJob.status, db.func.count(AnalysisJob.job_id))
        .group_by(AnalysisJob.status)
        .all()
    )
    status_counts = {status: count for status, count in status_counts_rows}
    queue_depth = status_counts.get("queued", 0)
    stale_leases = AnalysisJob.query.filter(
        AnalysisJob.status.in_(["running", "canceling"]),
        AnalysisJob.lease_expires_at.is_not(None),
        AnalysisJob.lease_expires_at < now,
    ).count()
    active_workers = (
        db.session.query(AnalysisJob.worker_id)
        .filter(
            AnalysisJob.status.in_(["running", "canceling"]),
            AnalysisJob.worker_id.is_not(None),
            AnalysisJob.lease_expires_at.is_not(None),
            AnalysisJob.lease_expires_at >= now,
        )
        .distinct()
        .count()
    )
    return {
        "generated_at": _to_iso(now),
        "queue_depth": queue_depth,
        "stale_leases": stale_leases,
        "active_workers": active_workers,
        "status_counts": status_counts,
    }


def _metrics_snapshot(now=None):
    now = now or _utcnow()
    job_stats = _job_stats_snapshot(now=now)
    history_count = AnalysisResult.query.count()
    return {
        "generated_at": now,
        "database_up": 1,
        "job_stats": job_stats,
        "history_count": history_count,
    }


def _prometheus_metrics_text(snapshot):
    lines = [
        "# HELP traffic_video_analysis_queue_depth Number of queued analysis jobs.",
        "# TYPE traffic_video_analysis_queue_depth gauge",
        f"traffic_video_analysis_queue_depth {snapshot['job_stats']['queue_depth']}",
        "# HELP traffic_video_analysis_stale_leases Number of stale worker leases.",
        "# TYPE traffic_video_analysis_stale_leases gauge",
        f"traffic_video_analysis_stale_leases {snapshot['job_stats']['stale_leases']}",
        "# HELP traffic_video_analysis_active_workers Number of active workers holding live leases.",
        "# TYPE traffic_video_analysis_active_workers gauge",
        f"traffic_video_analysis_active_workers {snapshot['job_stats']['active_workers']}",
        "# HELP traffic_video_analysis_history_records_total Number of persisted analysis history records.",
        "# TYPE traffic_video_analysis_history_records_total gauge",
        f"traffic_video_analysis_history_records_total {snapshot['history_count']}",
        "# HELP traffic_video_analysis_database_up Database connectivity check for the metrics scrape.",
        "# TYPE traffic_video_analysis_database_up gauge",
        f"traffic_video_analysis_database_up {snapshot['database_up']}",
        "# HELP traffic_video_analysis_jobs_total Number of analysis jobs by status.",
        "# TYPE traffic_video_analysis_jobs_total gauge",
    ]
    for status, count in sorted(snapshot["job_stats"]["status_counts"].items()):
        lines.append(f'traffic_video_analysis_jobs_total{{status="{status}"}} {count}')
    generated_at = int(snapshot["generated_at"].timestamp())
    lines.append("# HELP traffic_video_analysis_metrics_generated_at Unix timestamp when metrics were generated.")
    lines.append("# TYPE traffic_video_analysis_metrics_generated_at gauge")
    lines.append(f"traffic_video_analysis_metrics_generated_at {generated_at}")
    return "\n".join(lines) + "\n"
