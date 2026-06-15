import datetime
import json
import os
import uuid
from urllib.parse import urlparse

from flask import Response, g, jsonify, request, send_from_directory
from sqlalchemy import text
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from backend.core import (
    ALLOWED_CAMERA_URL_SCHEMES,
    ALLOWED_VIDEO_EXTENSIONS,
    OUTPUT_FOLDER,
    TEST_ROUTES_ENABLED,
    UPLOAD_FOLDER,
    _file_extension,
    _is_truthy,
    _to_iso,
    _utcnow,
    app,
    db,
)
from backend.models import AnalysisJob, AnalysisResult
from backend.observability import (
    _failure_reason,
    _job_stats_snapshot,
    _metrics_snapshot,
    _prometheus_metrics_text,
    diagnostics_snapshot,
    log_event,
)
from backend.services import (
    _cleanup_uploaded_file,
    _job_video_source,
    _persist_analysis_record,
    analyze_with_gpt,
    execute_analysis,
    prune_terminal_jobs,
    run_local_analysis,
)

UNSUPPORTED_CAMERA_URL_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}


class ApiError(Exception):
    def __init__(self, message, code, status_code=400, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


def _error_response(message, code, status_code, details=None):
    payload = {
        "error": message,
        "error_code": code,
        "status": status_code,
    }
    if details:
        payload["details"] = details
    return jsonify(payload), status_code


def _normalize_correlation_id(value):
    value = (value or "").strip()
    if not value:
        return uuid.uuid4().hex
    return value[:128]


def _current_correlation_id():
    return getattr(g, "correlation_id", None) or _normalize_correlation_id(None)


@app.before_request
def attach_correlation_id():
    g.correlation_id = _normalize_correlation_id(request.headers.get("X-Correlation-ID"))


@app.after_request
def add_correlation_id_header(response):
    response.headers.setdefault("X-Correlation-ID", _current_correlation_id())
    return response


def _serialize_job(job):
    payload = {
        "job_id": job.job_id,
        "correlation_id": job.correlation_id,
        "status": job.status,
        "analysis_name": job.analysis_name,
        "source_kind": job.source_kind,
        "cancel_requested": bool(job.cancel_requested),
        "progress_percent": job.progress_percent,
        "progress_message": job.progress_message,
        "worker_id": job.worker_id,
        "retry_count": int(job.retry_count or 0),
        "last_retried_at": _to_iso(job.last_retried_at),
        "created_at": _to_iso(job.created_at),
        "updated_at": _to_iso(job.updated_at),
        "started_at": _to_iso(job.started_at),
        "completed_at": _to_iso(job.completed_at),
    }
    if job.error:
        payload["error"] = job.error
    if job.result_json:
        payload["result"] = json.loads(job.result_json)
    return payload


def _parse_limit(raw_value, default=20, maximum=100):
    if raw_value in {None, ""}:
        return default
    try:
        limit = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ApiError("limit must be an integer", "invalid_query_parameter", 400, {"parameter": "limit"}) from exc
    if limit < 1 or limit > maximum:
        raise ApiError(
            f"limit must be between 1 and {maximum}",
            "invalid_query_parameter",
            400,
            {"parameter": "limit"},
        )
    return limit


def _parse_offset(raw_value):
    if raw_value in {None, ""}:
        return 0
    try:
        offset = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ApiError("offset must be an integer", "invalid_query_parameter", 400, {"parameter": "offset"}) from exc
    if offset < 0:
        raise ApiError("offset must be zero or greater", "invalid_query_parameter", 400, {"parameter": "offset"})
    return offset


def _job_list_query(status_filter=None, source_kind=None, analysis_name=None):
    query = AnalysisJob.query
    if status_filter:
        statuses = [status.strip() for status in status_filter.split(",") if status.strip()]
        if statuses:
            query = query.filter(AnalysisJob.status.in_(statuses))
    if source_kind:
        query = query.filter(AnalysisJob.source_kind == source_kind)
    if analysis_name:
        query = query.filter(AnalysisJob.analysis_name.is_not(None), AnalysisJob.analysis_name.ilike(f"%{analysis_name}%"))
    return query


def _prepare_analysis_request(req):
    temp_path = None
    if "video" in req.files:
        file = req.files["video"]
        if file.filename == "":
            raise ApiError("Empty filename", "invalid_upload", 400)
        extension = _file_extension(file.filename)
        if extension not in ALLOWED_VIDEO_EXTENSIONS:
            raise ApiError(f"Unsupported video file extension: .{extension or 'unknown'}", "invalid_upload_extension", 400)
        safe_name = secure_filename(file.filename) or "traffic_video"
        temp_name = f"{uuid.uuid4().hex}_{safe_name}"
        temp_path = os.path.join(UPLOAD_FOLDER, temp_name)
        file.save(temp_path)
        video_path = temp_path
        source_kind = "upload"
    elif "camera_url" in req.form:
        video_path = request.form.get("camera_url")
        if not video_path:
            raise ApiError("No camera URL provided", "missing_camera_url", 400)
        if video_path.isdigit():
            video_path = int(video_path)
        else:
            parsed = urlparse(video_path)
            host = (parsed.netloc or "").lower()
            if host.startswith("www."):
                normalized_host = host[4:]
            else:
                normalized_host = host
            if normalized_host in UNSUPPORTED_CAMERA_URL_HOSTS:
                raise ApiError(
                    "YouTube page URLs are not supported. Use an integer device index or a direct rtsp/http/https camera stream URL.",
                    "unsupported_camera_url_host",
                    400,
                )
            if parsed.scheme.lower() not in ALLOWED_CAMERA_URL_SCHEMES or not parsed.netloc:
                raise ApiError(
                    "Unsupported camera URL. Use an integer device index or an rtsp/http/https URL.",
                    "invalid_camera_url",
                    400,
                )
        source_kind = "camera_url"
    else:
        raise ApiError("No video file or camera URL provided", "missing_video_source", 400)

    start_date = req.form.get("start_date")
    start_time = req.form.get("start_time")
    if start_date and start_time:
        start_dt = datetime.datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
    else:
        start_dt = datetime.datetime.now()

    return {
        "video_path": video_path,
        "temp_path": temp_path,
        "source_kind": source_kind,
        "start_dt": start_dt,
        "analysis_name": req.form.get("analysis_name", "").strip() or None,
        "save_annotated": _is_truthy(req.form.get("save_annotated")),
    }


def _get_job_or_404(job_id):
    job = db.session.get(AnalysisJob, job_id)
    if not job:
        return None, _error_response("Analysis job not found", "job_not_found", 404)
    return job, None


def _reset_job_for_retry(job):
    now = _utcnow()
    job.status = "queued"
    job.cancel_requested = False
    job.progress_percent = 0
    job.progress_message = "Queued for retry."
    job.error = None
    job.result_json = None
    job.retry_count = int(job.retry_count or 0) + 1
    job.last_retried_at = now
    job.worker_id = None
    job.heartbeat_at = None
    job.lease_expires_at = None
    job.started_at = None
    job.completed_at = None
    job.updated_at = now


@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(exc):
    log_event("request_too_large", level="warning", error=str(exc))
    return _error_response("Uploaded file exceeds the maximum allowed size.", "request_too_large", 413)


@app.route("/analyze", methods=["POST"])
def analyze():
    temp_path = None
    try:
        prepared = _prepare_analysis_request(request)
        temp_path = prepared["temp_path"]
        response = execute_analysis(
            video_path=prepared["video_path"],
            start_dt=prepared["start_dt"],
            save_annotated=prepared["save_annotated"],
            analysis_name=prepared["analysis_name"],
        )
        _persist_analysis_record(response, prepared["analysis_name"])
        return jsonify(response)
    except RequestEntityTooLarge as exc:
        raise exc
    except ApiError as exc:
        log_event("analysis_request_invalid", level="warning", error=exc.message, error_code=exc.code)
        return _error_response(exc.message, exc.code, exc.status_code, exc.details)
    except Exception as exc:
        app.logger.exception("Unhandled error in /analyze")
        log_event("analysis_request_failed", level="error", error=str(exc))
        return _error_response(str(exc), "analysis_request_failed", 500)
    finally:
        _cleanup_uploaded_file(temp_path)


@app.route("/analysis-jobs", methods=["POST"])
def create_analysis_job():
    try:
        prepared = _prepare_analysis_request(request)
        created_at = _utcnow()
        job = AnalysisJob(
            job_id=uuid.uuid4().hex,
            correlation_id=_current_correlation_id(),
            status="queued",
            analysis_name=prepared["analysis_name"],
            input_path=str(prepared["video_path"]),
            source_kind=prepared["source_kind"],
            save_annotated=prepared["save_annotated"],
            cancel_requested=False,
            progress_percent=0,
            progress_message="Queued for analysis.",
            error=None,
            result_json=None,
            retry_count=0,
            last_retried_at=None,
            worker_id=None,
            heartbeat_at=None,
            lease_expires_at=None,
            start_dt=prepared["start_dt"],
            created_at=created_at,
            updated_at=created_at,
        )
        db.session.add(job)
        db.session.commit()
        db.session.refresh(job)
        log_event(
            "analysis_job_created",
            job_id=job.job_id,
            correlation_id=job.correlation_id,
            status=job.status,
            source_kind=job.source_kind,
            save_annotated=job.save_annotated,
            analysis_name=job.analysis_name,
        )
        return jsonify(_serialize_job(job)), 202
    except RequestEntityTooLarge as exc:
        raise exc
    except ApiError as exc:
        log_event("analysis_job_invalid", level="warning", error=exc.message, error_code=exc.code)
        return _error_response(exc.message, exc.code, exc.status_code, exc.details)
    except Exception as exc:
        app.logger.exception("Unhandled error in /analysis-jobs")
        log_event("analysis_job_create_failed", level="error", error=str(exc))
        return _error_response(str(exc), "analysis_job_create_failed", 500)


@app.route("/analysis-jobs", methods=["GET"])
def list_analysis_jobs():
    try:
        limit = _parse_limit(request.args.get("limit"))
        offset = _parse_offset(request.args.get("offset"))
        status_filter = request.args.get("status", "").strip() or None
        source_kind = request.args.get("source_kind", "").strip() or None
        analysis_name = request.args.get("analysis_name", "").strip() or None
        query = _job_list_query(status_filter=status_filter, source_kind=source_kind, analysis_name=analysis_name)
        total = query.count()
        jobs = query.order_by(AnalysisJob.created_at.desc()).offset(offset).limit(limit).all()
        return jsonify(
            {
                "jobs": [_serialize_job(job) for job in jobs],
                "limit": limit,
                "offset": offset,
                "count": len(jobs),
                "total": total,
                "filters": {"status": status_filter, "source_kind": source_kind, "analysis_name": analysis_name},
            }
        )
    except ApiError as exc:
        return _error_response(exc.message, exc.code, exc.status_code, exc.details)


@app.route("/analysis-jobs/failures", methods=["GET"])
def list_recent_failures():
    try:
        limit = _parse_limit(request.args.get("limit"), default=10)
        offset = _parse_offset(request.args.get("offset"))
    except ApiError as exc:
        return _error_response(exc.message, exc.code, exc.status_code, exc.details)

    query = AnalysisJob.query.filter(AnalysisJob.status == "failed").order_by(
        AnalysisJob.completed_at.desc(),
        AnalysisJob.updated_at.desc(),
    )
    total = query.count()
    failures = query.offset(offset).limit(limit).all()
    return jsonify(
        {
            "failures": [
                {
                    **_serialize_job(job),
                    "failure_reason": _failure_reason(job.error),
                }
                for job in failures
            ],
            "limit": limit,
            "offset": offset,
            "count": len(failures),
            "total": total,
        }
    )


@app.route("/analysis-jobs/workers", methods=["GET"])
def list_active_workers():
    now = _utcnow()
    now_naive = now.replace(tzinfo=None)
    jobs = (
        AnalysisJob.query.filter(
            AnalysisJob.status.in_(["running", "canceling"]),
            AnalysisJob.worker_id.is_not(None),
        )
        .order_by(AnalysisJob.worker_id.asc(), AnalysisJob.updated_at.desc())
        .all()
    )
    workers = {}
    for job in jobs:
        worker = workers.setdefault(
            job.worker_id,
            {
                "worker_id": job.worker_id,
                "active_job_count": 0,
                "last_heartbeat_at": None,
                "lease_expires_at": None,
                "stale": False,
                "jobs": [],
                "_last_heartbeat_raw": None,
                "_lease_expires_raw": None,
            },
        )
        worker["active_job_count"] += 1
        worker["jobs"].append(
            {
                "job_id": job.job_id,
                "correlation_id": job.correlation_id,
                "status": job.status,
                "analysis_name": job.analysis_name,
                "progress_percent": job.progress_percent,
                "progress_message": job.progress_message,
                "heartbeat_at": _to_iso(job.heartbeat_at),
                "lease_expires_at": _to_iso(job.lease_expires_at),
            }
        )
        if job.heartbeat_at and (
            worker["_last_heartbeat_raw"] is None or job.heartbeat_at > worker["_last_heartbeat_raw"]
        ):
            worker["_last_heartbeat_raw"] = job.heartbeat_at
            worker["last_heartbeat_at"] = _to_iso(job.heartbeat_at)
        if job.lease_expires_at and (
            worker["_lease_expires_raw"] is None or job.lease_expires_at > worker["_lease_expires_raw"]
        ):
            worker["_lease_expires_raw"] = job.lease_expires_at
            worker["lease_expires_at"] = _to_iso(job.lease_expires_at)
        if job.lease_expires_at and job.lease_expires_at < now_naive:
            worker["stale"] = True

    payload_workers = []
    for worker in workers.values():
        worker.pop("_last_heartbeat_raw", None)
        worker.pop("_lease_expires_raw", None)
        payload_workers.append(worker)
    return jsonify({"workers": payload_workers, "count": len(payload_workers), "generated_at": _to_iso(now)})


@app.route("/analysis-jobs/<job_id>", methods=["GET"])
def get_analysis_job(job_id):
    job, error_response = _get_job_or_404(job_id)
    if error_response:
        return error_response
    return jsonify(_serialize_job(job))


@app.route("/analysis-jobs/stats", methods=["GET"])
def get_analysis_job_stats():
    return jsonify(_job_stats_snapshot())


@app.route("/analysis-jobs/prune", methods=["POST"])
def prune_analysis_jobs():
    payload = request.get_json(silent=True) or {}
    retention_hours = payload.get("retention_hours")
    dry_run = _is_truthy(payload.get("dry_run"))
    if retention_hours is not None:
        try:
            retention_hours = int(retention_hours)
        except (TypeError, ValueError):
            return _error_response(
                "retention_hours must be an integer",
                "invalid_query_parameter",
                400,
                {"parameter": "retention_hours"},
            )
        if retention_hours < 1:
            return _error_response(
                "retention_hours must be at least 1",
                "invalid_query_parameter",
                400,
                {"parameter": "retention_hours"},
            )
    result = prune_terminal_jobs(retention_hours=retention_hours, dry_run=dry_run)
    log_event(
        "analysis_jobs_pruned",
        retention_hours=result["retention_hours"],
        dry_run=result["dry_run"],
        deleted_jobs=result["deleted_jobs"],
        deleted_output_files=result["deleted_output_files"],
    )
    return jsonify(result)


@app.route("/analysis-jobs/<job_id>/cancel", methods=["POST"])
def cancel_analysis_job(job_id):
    job, error_response = _get_job_or_404(job_id)
    if error_response:
        return error_response

    if job.status in {"completed", "failed", "canceled"}:
        return jsonify(_serialize_job(job))

    job.cancel_requested = True
    if job.status == "queued":
        job.status = "canceled"
        job.progress_message = "Canceled before processing started."
        job.completed_at = _utcnow()
        if job.source_kind == "upload":
            _cleanup_uploaded_file(job.input_path)
    else:
        job.status = "canceling"
        job.progress_message = "Cancel requested. Waiting for the worker to stop."
    job.updated_at = _utcnow()
    db.session.commit()
    log_event(
        "analysis_job_cancel_requested",
        job_id=job.job_id,
        status=job.status,
        cancel_requested=job.cancel_requested,
    )
    return jsonify(_serialize_job(job))


@app.route("/analysis-jobs/<job_id>/retry", methods=["POST"])
def retry_analysis_job(job_id):
    job, error_response = _get_job_or_404(job_id)
    if error_response:
        return error_response

    if job.status not in {"failed", "canceled"}:
        return _error_response("Only failed or canceled jobs can be retried", "job_retry_conflict", 409)

    if job.source_kind == "upload":
        if not job.input_path or not os.path.exists(job.input_path):
            return _error_response("Uploaded video is no longer available for retry", "job_retry_source_unavailable", 409)
    elif job.source_kind != "camera_url":
        return _error_response("Unsupported job source for retry", "job_retry_source_unsupported", 409)

    _reset_job_for_retry(job)
    db.session.commit()
    log_event(
        "analysis_job_retried",
        job_id=job.job_id,
        correlation_id=job.correlation_id,
        status=job.status,
        source_kind=job.source_kind,
        retry_count=job.retry_count,
    )
    return jsonify(_serialize_job(job))


@app.route("/health", methods=["GET"])
def health():
    try:
        db.session.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        database_status = "error"
    return jsonify(
        {
            "status": "ok" if database_status == "ok" else "degraded",
            "database": database_status,
            "jobs": _job_stats_snapshot(),
        }
    )


@app.route("/metrics", methods=["GET"])
def metrics():
    snapshot = _metrics_snapshot()
    body = _prometheus_metrics_text(snapshot)
    return Response(body, mimetype="text/plain; version=0.0.4; charset=utf-8")


@app.route("/diagnostics", methods=["GET"])
def diagnostics():
    return jsonify(diagnostics_snapshot())


@app.route("/output/<filename>")
def output_file(filename):
    extension = os.path.splitext(filename)[1].lower()
    if extension == ".mp4":
        mimetype = "video/mp4"
    elif extension == ".webm":
        mimetype = "video/webm"
    else:
        mimetype = None
    return send_from_directory(OUTPUT_FOLDER, filename, mimetype=mimetype, as_attachment=False)


@app.route("/history", methods=["GET"])
def get_history():
    query = AnalysisResult.query
    analysis_name = request.args.get("analysis_name", "").strip() or None
    date_from = request.args.get("date_from", "").strip() or None
    date_to = request.args.get("date_to", "").strip() or None
    uses_query_shape = any(value is not None for value in [analysis_name, date_from, date_to]) or any(
        key in request.args for key in ("limit", "offset")
    )

    if analysis_name:
        query = query.filter(AnalysisResult.analysis_name.is_not(None), AnalysisResult.analysis_name.ilike(f"%{analysis_name}%"))

    if date_from:
        try:
            parsed_from = datetime.datetime.fromisoformat(date_from)
        except ValueError:
            return _error_response("date_from must be ISO-8601 compatible", "invalid_query_parameter", 400, {"parameter": "date_from"})
        query = query.filter(AnalysisResult.timestamp >= parsed_from)

    if date_to:
        try:
            parsed_to = datetime.datetime.fromisoformat(date_to)
        except ValueError:
            return _error_response("date_to must be ISO-8601 compatible", "invalid_query_parameter", 400, {"parameter": "date_to"})
        query = query.filter(AnalysisResult.timestamp <= parsed_to)

    query = query.order_by(AnalysisResult.timestamp.desc())

    if not uses_query_shape:
        results = query.limit(50).all()
        return jsonify([result.to_dict() for result in results])

    try:
        limit = _parse_limit(request.args.get("limit"), default=50)
        offset = _parse_offset(request.args.get("offset"))
    except ApiError as exc:
        return _error_response(exc.message, exc.code, exc.status_code, exc.details)

    total = query.count()
    results = query.offset(offset).limit(limit).all()
    return jsonify(
        {
            "records": [result.to_dict() for result in results],
            "limit": limit,
            "offset": offset,
            "count": len(results),
            "total": total,
            "filters": {
                "analysis_name": analysis_name,
                "date_from": date_from,
                "date_to": date_to,
            },
        }
    )


if TEST_ROUTES_ENABLED:
    @app.route("/test_analysis", methods=["POST"])
    def test_analysis():
        data = request.get_json() or {}
        analysis = run_local_analysis(data.get("time_series", []), data.get("counts", {}))
        return jsonify(analysis)


    @app.route("/test_gpt_analysis", methods=["GET"])
    def test_gpt_analysis():
        counts = {
            "Commercial Vehicles": 12,
            "High-End Vehicles": 18,
            "Low-End Vehicles": 5,
            "Mid-Range Vehicles": 15,
            "Motorcycle": 3,
            "Unclassified": 20,
        }
        time_series = [
            {
                "timestamp": "2024-07-07 09:00:00",
                "Commercial Vehicles": 3,
                "High-End Vehicles": 4,
                "Low-End Vehicles": 0,
                "Mid-Range Vehicles": 4,
                "Motorcycle": 1,
                "Unclassified": 0,
            },
            {
                "timestamp": "2024-07-07 10:00:00",
                "Commercial Vehicles": 4,
                "High-End Vehicles": 6,
                "Low-End Vehicles": 2,
                "Mid-Range Vehicles": 5,
                "Motorcycle": 1,
                "Unclassified": 10,
            },
            {
                "timestamp": "2024-07-07 11:00:00",
                "Commercial Vehicles": 5,
                "High-End Vehicles": 8,
                "Low-End Vehicles": 3,
                "Mid-Range Vehicles": 6,
                "Motorcycle": 1,
                "Unclassified": 20,
            },
        ]
        return jsonify({"gpt_recommendations": analyze_with_gpt(counts, time_series)})
