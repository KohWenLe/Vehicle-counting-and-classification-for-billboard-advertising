import datetime
import json
import os

from backend.core import (
    DEFAULT_JOB_RETENTION_HOURS,
    DEFAULT_PIPELINE_CLASSIFICATION_THRESHOLD,
    DEFAULT_PIPELINE_CLASSIFICATION_VOTE_SAMPLES,
    DEFAULT_PIPELINE_CLASSIFIER_PATH,
    DEFAULT_PIPELINE_CONFIDENCE_THRESHOLD,
    DEFAULT_PIPELINE_DETECTION_INTERVAL,
    DEFAULT_PIPELINE_IMGSZ,
    DEFAULT_PIPELINE_MIN_CROP,
    DEFAULT_PIPELINE_MODEL_PATH,
    DEFAULT_PIPELINE_NMS_IOU,
    DEFAULT_PIPELINE_PROGRESS_REPORT_FRAMES,
    DEFAULT_PIPELINE_RESIZE_DIM,
    DEFAULT_PIPELINE_ROI_POINTS,
    DEFAULT_PIPELINE_TRACKER_BACKEND,
    DEFAULT_PIPELINE_TRACKER_MIN_HITS,
    DEFAULT_PIPELINE_TRACK_CONF,
    OUTPUT_FOLDER,
    TERMINAL_JOB_STATUSES,
    _is_truthy,
    _to_iso,
    _utcnow,
    db,
)
from backend.models import AnalysisJob, AnalysisResult


def run_video_pipeline(video_path, start_dt, save_annotated, analysis_name, progress_callback=None, should_cancel=None):
    from pipeline import process_video

    return process_video(
        video_path,
        start_dt=start_dt,
        resize_dim=DEFAULT_PIPELINE_RESIZE_DIM,
        detection_interval=DEFAULT_PIPELINE_DETECTION_INTERVAL,
        detection_imgsz=DEFAULT_PIPELINE_IMGSZ,
        progress_report_frames=DEFAULT_PIPELINE_PROGRESS_REPORT_FRAMES,
        tracker_backend=DEFAULT_PIPELINE_TRACKER_BACKEND,
        tracker_min_hits=DEFAULT_PIPELINE_TRACKER_MIN_HITS,
        classification_vote_samples=DEFAULT_PIPELINE_CLASSIFICATION_VOTE_SAMPLES,
        confidence_threshold=DEFAULT_PIPELINE_CONFIDENCE_THRESHOLD,
        tracker_feed_conf=DEFAULT_PIPELINE_TRACK_CONF,
        nms_iou=DEFAULT_PIPELINE_NMS_IOU,
        classification_threshold=DEFAULT_PIPELINE_CLASSIFICATION_THRESHOLD,
        min_w=DEFAULT_PIPELINE_MIN_CROP,
        min_h=DEFAULT_PIPELINE_MIN_CROP,
        roi_points=DEFAULT_PIPELINE_ROI_POINTS,
        model_path=DEFAULT_PIPELINE_MODEL_PATH,
        classifier_path=DEFAULT_PIPELINE_CLASSIFIER_PATH,
        save_annotated=save_annotated,
        analysis_name=analysis_name,
        output_dir=OUTPUT_FOLDER,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
    )


def run_local_analysis(time_series, counts):
    from analysis import analyze_results

    return analyze_results(time_series, counts)


def _cleanup_uploaded_file(path):
    if path and isinstance(path, str) and os.path.exists(path):
        os.remove(path)


def _persist_analysis_record(result, analysis_name):
    peak = result.get("peak")
    recommendations = result.get("recommendations", [])
    record = AnalysisResult(
        user_id=None,
        counts=json.dumps(result["counts"]),
        peak_hour=peak["hour"] if peak else None,
        peak_count=peak["count"] if peak else None,
        recommendations=json.dumps(recommendations),
        analysis_name=analysis_name,
    )
    db.session.add(record)
    db.session.commit()


def _job_video_source(job):
    if job.source_kind == "camera_url" and isinstance(job.input_path, str) and job.input_path.isdigit():
        return int(job.input_path)
    return job.input_path


def _job_output_filename(job):
    if not job or not job.result_json:
        return None
    try:
        result = json.loads(job.result_json)
    except json.JSONDecodeError:
        return None
    output_name = result.get("annotated_video")
    if not output_name:
        return None
    return os.path.basename(output_name)


def prune_terminal_jobs(retention_hours=None, now=None, dry_run=False):
    now = now or _utcnow()
    retention_hours = DEFAULT_JOB_RETENTION_HOURS if retention_hours is None else retention_hours
    cutoff = now - datetime.timedelta(hours=retention_hours)
    jobs_to_delete = (
        AnalysisJob.query.filter(
            AnalysisJob.status.in_(TERMINAL_JOB_STATUSES),
            AnalysisJob.completed_at.is_not(None),
            AnalysisJob.completed_at < cutoff,
        )
        .order_by(AnalysisJob.completed_at.asc())
        .all()
    )
    deleted_output_files = 0
    deleted_job_ids = []
    for job in jobs_to_delete:
        output_name = _job_output_filename(job)
        if output_name:
            output_path = os.path.join(OUTPUT_FOLDER, output_name)
            if os.path.exists(output_path):
                deleted_output_files += 1
                if not dry_run:
                    os.remove(output_path)
        deleted_job_ids.append(job.job_id)
        if not dry_run:
            db.session.delete(job)
    if not dry_run and jobs_to_delete:
        db.session.commit()
    return {
        "deleted_jobs": len(jobs_to_delete),
        "deleted_output_files": deleted_output_files,
        "deleted_job_ids": deleted_job_ids,
        "cutoff": _to_iso(cutoff),
        "dry_run": dry_run,
        "retention_hours": retention_hours,
    }


def execute_analysis(video_path, start_dt, save_annotated, analysis_name, progress_callback=None, should_cancel=None):
    pipeline_result = run_video_pipeline(
        video_path,
        start_dt=start_dt,
        save_annotated=save_annotated,
        analysis_name=analysis_name,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
    )
    analysis = run_local_analysis(pipeline_result["time_series"], pipeline_result["counts"])
    try:
        gpt_recommendations = analyze_with_gpt(pipeline_result["counts"], pipeline_result["time_series"])
    except Exception as gpt_error:
        print(f"GPT API error: {gpt_error}")
        gpt_recommendations = None

    response = {
        "counts": pipeline_result["counts"],
        "time_series": pipeline_result["time_series"],
        "peak": analysis.get("peak") if analysis else None,
        "recommendations": analysis.get("recommendations", []) if analysis else [],
        "analysis_name": analysis_name,
    }
    confidence_summary = pipeline_result.get("classification_confidence")
    if confidence_summary:
        response["classification_confidence"] = confidence_summary
        weak_labels = sorted(
            label
            for label, payload in confidence_summary.items()
            if label != "Unclassified"
            and payload.get("mean_confidence") is not None
            and payload["mean_confidence"] < 0.55
        )
        if weak_labels and isinstance(response["recommendations"], list):
            response["recommendations"] = [
                *response["recommendations"],
                (
                    f"Note: classification confidence is low for {', '.join(weak_labels)} "
                    "(mean vote confidence below 0.55). Treat the class mix as indicative rather than exact."
                ),
            ]
    if pipeline_result.get("annotated_video"):
        response["annotated_video"] = pipeline_result["annotated_video"]
    if gpt_recommendations:
        response["gpt_recommendations"] = gpt_recommendations
    return response


def analyze_with_gpt(counts, time_series):
    if _is_truthy(os.getenv("TVA_DISABLE_GPT")):
        return None

    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        load_dotenv = None

    if load_dotenv:
        load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "sk-sample":
        return None

    import openai

    client = openai.OpenAI(api_key=api_key)
    prompt = (
        "You are a billboard advertising strategist. "
        "Given this vehicle traffic data, note that all counts and time series are cumulative totals up to each timestamp, not interval-based flows. "
        f"Total counts per class: {counts}. "
        f"Hourly time series sample: {time_series[:3]}.\n"
        "Instructions:\n"
        "- Briefly identify the peak hour and dominant class, in one sentence each.\n"
        "- List exactly 5 targeted advertisement recommendations for the most common audience.\n"
        "- Add a short practical explanation in 2 to 3 sentences.\n"
        "- Do not repeat raw counts in the final answer.\n"
        "- Keep the answer under 200 words.\n"
    )
    response = client.chat.completions.create(
        model="gpt-4.1-nano-2025-04-14",
        messages=[
            {"role": "system", "content": "You are a concise and expert billboard ad advisor."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=300,
        temperature=0.5,
    )
    return response.choices[0].message.content
