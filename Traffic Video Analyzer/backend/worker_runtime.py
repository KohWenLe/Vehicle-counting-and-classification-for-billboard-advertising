import datetime
import json
import os
import socket
import time
from types import SimpleNamespace

from backend.core import _utcnow, app, db
from backend.models import AnalysisJob
from backend.observability import diagnostics_snapshot, log_event
from backend.services import (
    _cleanup_uploaded_file,
    _job_video_source,
    _persist_analysis_record,
    execute_analysis,
    prune_terminal_jobs,
)


LEASE_SECONDS = int(os.getenv("TVA_WORKER_LEASE_SECONDS", "30"))
JOB_TIMEOUT_SECONDS = int(os.getenv("TVA_JOB_TIMEOUT_SECONDS", "7200"))
MAINTENANCE_INTERVAL_SECONDS = int(os.getenv("TVA_MAINTENANCE_INTERVAL_SECONDS", "300"))
PROGRESS_SAVE_INTERVAL_SECONDS = max(1, int(os.getenv("TVA_PROGRESS_SAVE_INTERVAL_SECONDS", "2")))
PROGRESS_SAVE_PERCENT_STEP = max(1, int(os.getenv("TVA_PROGRESS_SAVE_PERCENT_STEP", "5")))
_last_maintenance_at = None


def get_worker_id():
    configured = os.getenv("TVA_WORKER_ID", "").strip()
    if configured:
        return configured
    return f"{socket.gethostname()}-{os.getpid()}"


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value


def _job_timed_out(job, now=None):
    if JOB_TIMEOUT_SECONDS <= 0 or not job or not job.started_at:
        return False
    now = now or _utcnow()
    started_at = _as_utc(job.started_at)
    return (now - started_at).total_seconds() > JOB_TIMEOUT_SECONDS


def _duration_seconds(start, end):
    start = _as_utc(start)
    end = _as_utc(end)
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds())


def maybe_run_maintenance(now=None, force=False):
    global _last_maintenance_at

    now = now or _utcnow()
    if not force and _last_maintenance_at is not None:
        elapsed = (now - _as_utc(_last_maintenance_at)).total_seconds()
        if elapsed < MAINTENANCE_INTERVAL_SECONDS:
            return False

    with app.app_context():
        result = prune_terminal_jobs()
    _last_maintenance_at = now
    log_event(
        "analysis_job_maintenance_ran",
        deleted_jobs=result.get("deleted_jobs", 0),
        deleted_output_files=result.get("deleted_output_files", 0),
        retention_hours=result.get("retention_hours"),
    )
    return True


def log_worker_startup(worker_id=None):
    worker_id = worker_id or get_worker_id()
    with app.app_context():
        diagnostics = diagnostics_snapshot()
    path_statuses = {
        name: {
            "exists": payload.get("exists"),
            "writable": payload.get("writable"),
            "disk_status": payload.get("disk_status"),
        }
        for name, payload in diagnostics.get("paths", {}).items()
    }
    model_statuses = {
        name: payload.get("exists")
        for name, payload in diagnostics.get("models", {}).items()
    }
    log_event(
        "worker_startup",
        worker_id=worker_id,
        diagnostics_status=diagnostics.get("status"),
        pipeline_tracker_backend=diagnostics.get("configuration", {}).get("pipeline_tracker_backend"),
        path_statuses=path_statuses,
        model_statuses=model_statuses,
    )
    return diagnostics


def recover_abandoned_jobs(worker_id=None):
    del worker_id
    with app.app_context():
        now = _utcnow()
        stale_jobs = AnalysisJob.query.filter(
            AnalysisJob.status.in_(["running", "canceling"]),
            AnalysisJob.lease_expires_at.is_not(None),
            AnalysisJob.lease_expires_at < now,
        ).all()
        for job in stale_jobs:
            if _job_timed_out(job, now=now):
                job.status = "failed"
                job.error = "Analysis timed out."
                job.progress_message = "Analysis timed out while the worker was offline."
                job.completed_at = now
            elif job.cancel_requested:
                job.status = "canceled"
                job.error = "Analysis canceled."
                job.progress_message = "Canceled while the worker was offline."
                job.completed_at = now
            else:
                job.status = "queued"
                job.progress_message = "Re-queued after stale worker lease expired."
                job.completed_at = None
            job.worker_id = None
            job.heartbeat_at = None
            job.lease_expires_at = None
            job.updated_at = now
            job.started_at = None
        if stale_jobs:
            db.session.commit()
            log_event("analysis_jobs_recovered", recovered_jobs=len(stale_jobs))
        return len(stale_jobs)


def _lease_deadline(now=None):
    now = now or _utcnow()
    return now + datetime.timedelta(seconds=LEASE_SECONDS)


def _job_stop_reason(job_id, worker_id):
    job = db.session.get(AnalysisJob, job_id)
    if not job:
        return "missing"
    db.session.refresh(job)
    if job.cancel_requested:
        return "cancel_requested"
    if job.worker_id not in {None, worker_id}:
        return "worker_lost"
    if _job_timed_out(job):
        return "timed_out"
    return None


def _job_should_cancel(job_id, worker_id):
    job = db.session.get(AnalysisJob, job_id)
    if not job:
        return True
    db.session.refresh(job)
    return _job_stop_reason(job_id, worker_id) is not None


def _refresh_job_lease(job_id, worker_id, progress_percent=None, progress_message=None):
    job = db.session.get(AnalysisJob, job_id)
    if not job or job.worker_id != worker_id:
        return
    now = _utcnow()
    last_heartbeat = _as_utc(job.heartbeat_at)
    last_progress_percent = job.progress_percent
    should_persist = False
    next_progress_percent = None

    if progress_percent is not None:
        next_progress_percent = max(0, min(100, int(progress_percent)))
        if last_progress_percent is None or abs(next_progress_percent - last_progress_percent) >= PROGRESS_SAVE_PERCENT_STEP:
            should_persist = True

    if not last_heartbeat or (now - last_heartbeat).total_seconds() >= PROGRESS_SAVE_INTERVAL_SECONDS:
        should_persist = True

    lease_expires_at = _as_utc(job.lease_expires_at)
    if not lease_expires_at or (lease_expires_at - now).total_seconds() <= max(1, LEASE_SECONDS // 3):
        should_persist = True

    if not should_persist:
        return

    if next_progress_percent is not None:
        job.progress_percent = next_progress_percent
    if progress_message:
        job.progress_message = progress_message[:256]
    job.heartbeat_at = now
    job.lease_expires_at = _lease_deadline(now)
    job.updated_at = now
    db.session.commit()


def claim_next_job(worker_id=None):
    worker_id = worker_id or get_worker_id()
    with app.app_context():
        while True:
            now = _utcnow()
            candidate = (
                AnalysisJob.query.filter(
                    AnalysisJob.cancel_requested.is_(False),
                    (
                        ((AnalysisJob.status == "queued"))
                        | (
                            AnalysisJob.status.in_(["running", "canceling"])
                            & AnalysisJob.lease_expires_at.is_not(None)
                            & (AnalysisJob.lease_expires_at < now)
                        )
                    ),
                )
                .order_by(AnalysisJob.created_at.asc())
                .first()
            )
            if not candidate:
                return None
            if _job_timed_out(candidate, now=now):
                candidate.status = "failed"
                candidate.error = "Analysis timed out."
                candidate.progress_message = "Analysis timed out before a worker could resume it."
                candidate.completed_at = now
                candidate.updated_at = now
                candidate.worker_id = None
                candidate.heartbeat_at = None
                candidate.lease_expires_at = None
                db.session.commit()
                log_event("analysis_job_failed", level="error", job_id=candidate.job_id, error=candidate.error)
                continue

            updated_rows = (
                AnalysisJob.query.filter_by(job_id=candidate.job_id, cancel_requested=False)
                .filter(
                    ((AnalysisJob.status == "queued"))
                    | (
                        AnalysisJob.status.in_(["running", "canceling"])
                        & AnalysisJob.lease_expires_at.is_not(None)
                        & (AnalysisJob.lease_expires_at < now)
                    )
                )
                .update(
                    {
                        AnalysisJob.status: "running",
                        AnalysisJob.progress_percent: 0 if candidate.status == "queued" else candidate.progress_percent,
                        AnalysisJob.progress_message: (
                            "Starting analysis..."
                            if candidate.status == "queued"
                            else "Reclaimed stale analysis lease. Resuming work..."
                        ),
                        AnalysisJob.worker_id: worker_id,
                        AnalysisJob.started_at: now if candidate.started_at is None else candidate.started_at,
                        AnalysisJob.heartbeat_at: now,
                        AnalysisJob.lease_expires_at: _lease_deadline(now),
                        AnalysisJob.updated_at: now,
                    },
                    synchronize_session=False,
                )
            )
            db.session.commit()
            if updated_rows == 1:
                claimed_job = db.session.get(AnalysisJob, candidate.job_id)
                log_event(
                    "analysis_job_claimed",
                    job_id=claimed_job.job_id,
                    correlation_id=claimed_job.correlation_id,
                    worker_id=worker_id,
                    reclaimed=(candidate.status != "queued"),
                    queue_wait_seconds=_duration_seconds(claimed_job.created_at, claimed_job.started_at),
                )
                return SimpleNamespace(job_id=claimed_job.job_id, worker_id=worker_id)


def process_job(job_id, worker_id=None):
    worker_id = worker_id or get_worker_id()
    with app.app_context():
        job = db.session.get(AnalysisJob, job_id)
        if not job:
            return None

        try:
            result = execute_analysis(
                video_path=_job_video_source(job),
                start_dt=job.start_dt,
                save_annotated=job.save_annotated,
                analysis_name=job.analysis_name,
                progress_callback=lambda percent=None, message=None: _refresh_job_lease(
                    job_id, worker_id, percent, message
                ),
                should_cancel=lambda: _job_should_cancel(job_id, worker_id),
            )
            _persist_analysis_record(result, job.analysis_name)
            job = db.session.get(AnalysisJob, job_id)
            job.status = "completed"
            job.progress_percent = 100
            job.progress_message = "Analysis completed."
            job.result_json = json.dumps(result)
            job.error = None
            completed_at = _utcnow()
            job.updated_at = completed_at
            job.completed_at = completed_at
            job.heartbeat_at = completed_at
            job.lease_expires_at = _lease_deadline()
            db.session.commit()
            log_event(
                "analysis_job_completed",
                job_id=job_id,
                correlation_id=job.correlation_id,
                worker_id=worker_id,
                progress_percent=job.progress_percent,
                queue_wait_seconds=_duration_seconds(job.created_at, job.started_at),
                processing_seconds=_duration_seconds(job.started_at, job.completed_at),
            )
        except Exception as exc:
            job = db.session.get(AnalysisJob, job_id)
            if exc.__class__.__name__ == "AnalysisCancelled":
                stop_reason = _job_stop_reason(job_id, worker_id)
                if stop_reason == "timed_out":
                    job.status = "failed"
                    job.error = "Analysis timed out."
                    job.progress_message = "Analysis timed out."
                else:
                    job.status = "canceled"
                    job.error = "Analysis canceled."
                    job.progress_message = "Analysis canceled."
            else:
                app.logger.exception("Unhandled error in worker process_job")
                job.status = "failed"
                job.error = str(exc)
                job.progress_message = "Analysis failed."
            job.updated_at = _utcnow()
            job.completed_at = _utcnow()
            job.heartbeat_at = _utcnow()
            job.lease_expires_at = _lease_deadline()
            db.session.commit()
            log_event(
                "analysis_job_failed" if job.status == "failed" else "analysis_job_canceled",
                level="error" if job.status == "failed" else "warning",
                job_id=job_id,
                correlation_id=job.correlation_id,
                worker_id=worker_id,
                error=job.error,
                queue_wait_seconds=_duration_seconds(job.created_at, job.started_at),
                processing_seconds=_duration_seconds(job.started_at, job.completed_at),
            )
        finally:
            job = db.session.get(AnalysisJob, job_id)
            if job and job.source_kind == "upload":
                _cleanup_uploaded_file(job.input_path)

        return SimpleNamespace(job_id=job_id, worker_id=worker_id)


def process_next_job(worker_id=None):
    maybe_run_maintenance()
    claimed = claim_next_job(worker_id=worker_id)
    if not claimed:
        return None
    return process_job(claimed.job_id, worker_id=claimed.worker_id)


def run_worker_loop(poll_interval_seconds=2, worker_id=None):
    worker_id = worker_id or get_worker_id()
    log_worker_startup(worker_id=worker_id)
    maybe_run_maintenance(force=True)
    recover_abandoned_jobs(worker_id=worker_id)
    while True:
        maybe_run_maintenance()
        processed = process_next_job(worker_id=worker_id)
        if processed is None:
            time.sleep(poll_interval_seconds)
