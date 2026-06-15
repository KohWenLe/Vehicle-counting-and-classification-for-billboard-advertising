import json
import os
import shutil

from backend.core import (
    ALLOWED_CAMERA_URL_SCHEMES,
    ALLOWED_VIDEO_EXTENSIONS,
    BASE_DIR,
    DEFAULT_MAX_UPLOAD_BYTES,
    DEFAULT_PIPELINE_DETECTION_INTERVAL,
    DEFAULT_PIPELINE_PROGRESS_REPORT_FRAMES,
    DEFAULT_PIPELINE_RESIZE_DIM,
    DEFAULT_PIPELINE_TRACKER_BACKEND,
    OUTPUT_FOLDER,
    UPLOAD_FOLDER,
    app,
    db,
    _to_iso,
    _utcnow,
)
from backend.models import AnalysisJob, AnalysisResult


DEFAULT_DISK_WARN_BYTES = int(os.getenv("TVA_DISK_WARN_BYTES", str(5 * 1024 * 1024 * 1024)))
DEFAULT_DISK_CRITICAL_BYTES = int(os.getenv("TVA_DISK_CRITICAL_BYTES", str(1024 * 1024 * 1024)))


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


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=_utcnow().tzinfo)
    return value


def _duration_seconds(start, end):
    start = _as_utc(start)
    end = _as_utc(end)
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds())


def _average(values):
    values = [value for value in values if value is not None]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _failure_reason(error):
    normalized = (error or "").strip().lower()
    if "timed out" in normalized or "timeout" in normalized:
        return "timeout"
    if "cancel" in normalized:
        return "canceled"
    if "cannot open" in normalized or "stream" in normalized:
        return "source_unavailable"
    return "unknown"


def _job_duration_snapshot():
    terminal_jobs = AnalysisJob.query.filter(
        AnalysisJob.status.in_(["completed", "failed"]),
        AnalysisJob.completed_at.is_not(None),
    ).all()
    queue_waits = [_duration_seconds(job.created_at, job.started_at) for job in terminal_jobs]
    processing_durations = [_duration_seconds(job.started_at, job.completed_at) for job in terminal_jobs]
    failure_counts = {}
    for job in terminal_jobs:
        if job.status != "failed":
            continue
        reason = _failure_reason(job.error)
        failure_counts[reason] = failure_counts.get(reason, 0) + 1
    retry_total = sum(int(value or 0) for (value,) in db.session.query(AnalysisJob.retry_count).all())
    return {
        "queue_wait_seconds_avg": _average(queue_waits),
        "processing_seconds_avg": _average(processing_durations),
        "failure_counts": failure_counts,
        "retry_total": retry_total,
    }


def _metrics_snapshot(now=None):
    now = now or _utcnow()
    job_stats = _job_stats_snapshot(now=now)
    history_count = AnalysisResult.query.count()
    return {
        "generated_at": now,
        "database_up": 1,
        "job_stats": job_stats,
        "durations": _job_duration_snapshot(),
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
    lines.extend(
        [
            "# HELP traffic_video_analysis_queue_wait_seconds_avg Average queue wait for completed or failed jobs.",
            "# TYPE traffic_video_analysis_queue_wait_seconds_avg gauge",
            f"traffic_video_analysis_queue_wait_seconds_avg {snapshot['durations']['queue_wait_seconds_avg']:.3f}",
            "# HELP traffic_video_analysis_processing_seconds_avg Average processing duration for completed or failed jobs.",
            "# TYPE traffic_video_analysis_processing_seconds_avg gauge",
            f"traffic_video_analysis_processing_seconds_avg {snapshot['durations']['processing_seconds_avg']:.3f}",
            "# HELP traffic_video_analysis_failures_total Number of failed jobs by reason.",
            "# TYPE traffic_video_analysis_failures_total gauge",
        ]
    )
    for reason, count in sorted(snapshot["durations"]["failure_counts"].items()):
        lines.append(f'traffic_video_analysis_failures_total{{reason="{reason}"}} {count}')
    lines.extend(
        [
            "# HELP traffic_video_analysis_job_retries_total Number of retry attempts recorded on terminal jobs.",
            "# TYPE traffic_video_analysis_job_retries_total counter",
            f"traffic_video_analysis_job_retries_total {snapshot['durations']['retry_total']}",
        ]
    )
    generated_at = int(snapshot["generated_at"].timestamp())
    lines.append("# HELP traffic_video_analysis_metrics_generated_at Unix timestamp when metrics were generated.")
    lines.append("# TYPE traffic_video_analysis_metrics_generated_at gauge")
    lines.append(f"traffic_video_analysis_metrics_generated_at {generated_at}")
    return "\n".join(lines) + "\n"


def _disk_status(free_bytes):
    if free_bytes is None:
        return "unavailable"
    if free_bytes <= DEFAULT_DISK_CRITICAL_BYTES:
        return "critical"
    if free_bytes <= DEFAULT_DISK_WARN_BYTES:
        return "warning"
    return "ok"


def _path_diagnostic(path):
    exists = os.path.exists(path)
    writable = os.access(path, os.W_OK) if exists else False
    try:
        usage = shutil.disk_usage(path if exists else os.path.dirname(path) or BASE_DIR)
        free_bytes = usage.free
    except OSError:
        free_bytes = None
    return {
        "path": path,
        "exists": exists,
        "writable": writable,
        "free_bytes": free_bytes,
        "disk_status": _disk_status(free_bytes),
    }


def _model_diagnostic(filename):
    path = os.path.join(BASE_DIR, filename)
    return {
        "path": path,
        "exists": os.path.exists(path),
    }


def diagnostics_snapshot():
    paths = {
        "upload_folder": _path_diagnostic(UPLOAD_FOLDER),
        "output_folder": _path_diagnostic(OUTPUT_FOLDER),
    }
    models = {
        "yolo": _model_diagnostic(os.getenv("TVA_YOLO_MODEL", "yolo11n.pt")),
        "classifier": _model_diagnostic(os.getenv("TVA_CLASSIFIER_MODEL", "mobilenetv3_original.keras")),
    }
    degraded = (
        any(
            not value["exists"] or not value["writable"] or value["disk_status"] in {"warning", "critical", "unavailable"}
            for value in paths.values()
        )
        or any(not value["exists"] for value in models.values())
    )
    return {
        "generated_at": _to_iso(_utcnow()),
        "status": "degraded" if degraded else "ok",
        "configuration": {
            "max_upload_bytes": DEFAULT_MAX_UPLOAD_BYTES,
            "allowed_video_extensions": sorted(ALLOWED_VIDEO_EXTENSIONS),
            "allowed_camera_url_schemes": sorted(ALLOWED_CAMERA_URL_SCHEMES),
            "pipeline_resize_dim": list(DEFAULT_PIPELINE_RESIZE_DIM),
            "pipeline_detection_interval": DEFAULT_PIPELINE_DETECTION_INTERVAL,
            "pipeline_progress_report_frames": DEFAULT_PIPELINE_PROGRESS_REPORT_FRAMES,
            "pipeline_tracker_backend": DEFAULT_PIPELINE_TRACKER_BACKEND,
            "disk_warn_bytes": DEFAULT_DISK_WARN_BYTES,
            "disk_critical_bytes": DEFAULT_DISK_CRITICAL_BYTES,
        },
        "paths": paths,
        "models": models,
    }
