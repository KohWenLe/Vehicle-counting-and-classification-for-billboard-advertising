import importlib
import datetime
import json
import os
import shutil
import sys
import types
import unittest
import uuid
from io import BytesIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def fake_process_video(video_path, start_dt=None, save_annotated=False, analysis_name=None, **kwargs):
    annotated_video = None
    if save_annotated:
        output_dir = Path(os.environ["TVA_OUTPUT_FOLDER"])
        output_dir.mkdir(parents=True, exist_ok=True)
        annotated_path = output_dir / f"{analysis_name or 'analysis'}.mp4"
        annotated_path.write_bytes(b"fake-video")
        annotated_video = annotated_path.name

    return {
        "counts": {
            "Commercial Vehicles": 3,
            "High-End Vehicles": 1,
            "Low-End Vehicles": 0,
            "Mid-Range Vehicles": 2,
            "Motorcycle": 0,
            "Unclassified": 0,
        },
        "time_series": [
            {
                "timestamp": "2024-07-07 09:00:00",
                "Commercial Vehicles": 1,
                "High-End Vehicles": 0,
                "Low-End Vehicles": 0,
                "Mid-Range Vehicles": 1,
                "Motorcycle": 0,
                "Unclassified": 0,
            },
            {
                "timestamp": "2024-07-07 09:05:00",
                "Commercial Vehicles": 3,
                "High-End Vehicles": 1,
                "Low-End Vehicles": 0,
                "Mid-Range Vehicles": 2,
                "Motorcycle": 0,
                "Unclassified": 0,
            },
        ],
        "annotated_video": annotated_video,
    }


class AnalyzeRouteTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / "tests_artifacts"
        temp_root.mkdir(exist_ok=True)
        self.temp_path = temp_root / f"run_{uuid.uuid4().hex}"
        self.temp_path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.temp_path, True)

        os.environ["TVA_DATABASE_URI"] = f"sqlite:///{(self.temp_path / 'test.db').as_posix()}"
        os.environ["TVA_UPLOAD_FOLDER"] = str(self.temp_path / "uploads")
        os.environ["TVA_OUTPUT_FOLDER"] = str(self.temp_path / "output")
        os.environ["TVA_DISABLE_GPT"] = "1"

        fake_pipeline = types.ModuleType("pipeline")
        fake_pipeline.process_video = fake_process_video
        sys.modules["pipeline"] = fake_pipeline
        self.addCleanup(sys.modules.pop, "pipeline", None)

        fake_analysis = types.ModuleType("analysis")
        fake_analysis.analyze_results = lambda time_series, counts: {
            "peak": {"hour": 9, "count": 6},
            "recommendations": ["Use commuter-focused ad creative."],
        }
        sys.modules["analysis"] = fake_analysis
        self.addCleanup(sys.modules.pop, "analysis", None)

        sys.modules.pop("app", None)
        sys.modules.pop("worker", None)
        self.app_module = importlib.import_module("app")
        self.worker_module = importlib.import_module("worker")

        self.app_module.app.config["TESTING"] = True
        with self.app_module.app.app_context():
            self.app_module.db.drop_all()
            self.app_module.db.create_all()

        self.client = self.app_module.app.test_client()

    def tearDown(self):
        for key in ["TVA_DATABASE_URI", "TVA_UPLOAD_FOLDER", "TVA_OUTPUT_FOLDER", "TVA_DISABLE_GPT"]:
            os.environ.pop(key, None)
        sys.modules.pop("app", None)
        sys.modules.pop("worker", None)

    def test_analyze_returns_peak_history_and_annotated_video_details(self):
        with mock.patch.object(self.app_module, "analyze_with_gpt", return_value=None):
            response = self.client.post(
                "/analyze",
                data={
                    "video": (BytesIO(b"video-bytes"), "traffic.mp4"),
                    "analysis_name": "weekday-am",
                    "save_annotated": "true",
                    "start_date": "2024-07-07",
                    "start_time": "09:00",
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["peak"], {"hour": 9, "count": 6})
        self.assertEqual(payload["analysis_name"], "weekday-am")
        self.assertEqual(payload["annotated_video"], "weekday-am.mp4")
        self.assertIn("recommendations", payload)

        history_response = self.client.get("/history")
        self.assertEqual(history_response.status_code, 200)
        history = history_response.get_json()
        self.assertEqual(history[0]["analysis_name"], "weekday-am")

    def test_output_route_serves_generated_mp4_with_video_mimetype(self):
        with mock.patch.object(self.app_module, "analyze_with_gpt", return_value=None):
            response = self.client.post(
                "/analyze",
                data={
                    "video": (BytesIO(b"video-bytes"), "traffic.mp4"),
                    "analysis_name": "weekday-am",
                    "save_annotated": "true",
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)

        output_response = self.client.get("/output/weekday-am.mp4")
        self.assertEqual(output_response.status_code, 200)
        self.assertEqual(output_response.mimetype, "video/mp4")
        self.assertEqual(output_response.data, b"fake-video")
        output_response.close()

    def test_upload_rejects_unsupported_file_extension(self):
        response = self.client.post(
            "/analysis-jobs",
            data={
                "video": (BytesIO(b"video-bytes"), "traffic.txt"),
                "analysis_name": "bad-file",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported video file extension", response.get_json()["error"])

    def test_upload_rejects_invalid_camera_url_scheme(self):
        response = self.client.post(
            "/analysis-jobs",
            data={
                "camera_url": "ftp://traffic-camera.local/stream",
                "analysis_name": "bad-camera",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported camera URL", response.get_json()["error"])
        self.assertEqual(response.get_json()["error_code"], "invalid_camera_url")

    def test_upload_rejects_youtube_page_urls(self):
        response = self.client.post(
            "/analysis-jobs",
            data={
                "camera_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "analysis_name": "youtube-link",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("YouTube page URLs are not supported", response.get_json()["error"])
        self.assertEqual(response.get_json()["error_code"], "unsupported_camera_url_host")

    def test_upload_rejects_request_over_size_limit(self):
        self.app_module.app.config["MAX_CONTENT_LENGTH"] = 8

        response = self.client.post(
            "/analysis-jobs",
            data={
                "video": (BytesIO(b"video-bytes-too-large"), "traffic.mp4"),
                "analysis_name": "too-big",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 413)

    def test_analysis_job_route_enqueues_without_running_in_app_process(self):
        with mock.patch.object(self.app_module.app.logger, "info") as info_log:
            create_response = self.client.post(
                "/analysis-jobs",
                data={
                    "video": (BytesIO(b"video-bytes"), "traffic.mp4"),
                    "analysis_name": "pm-commute",
                    "save_annotated": "true",
                    "start_date": "2024-07-07",
                    "start_time": "17:00",
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(create_response.status_code, 202)
        created_job = create_response.get_json()
        self.assertEqual(created_job["status"], "queued")
        self.assertEqual(created_job["progress_percent"], 0)
        self.assertNotIn("result", created_job)
        self.assertTrue(info_log.called)
        self.assertIn('"event":"analysis_job_created"', info_log.call_args_list[0].args[0])

        status_response = self.client.get(f"/analysis-jobs/{created_job['job_id']}")
        self.assertEqual(status_response.status_code, 200)
        payload = status_response.get_json()
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["analysis_name"], "pm-commute")

    def test_analysis_job_preserves_request_correlation_id(self):
        create_response = self.client.post(
            "/analysis-jobs",
            headers={"X-Correlation-ID": "campaign-trace-123"},
            data={
                "video": (BytesIO(b"video-bytes"), "traffic.mp4"),
                "analysis_name": "trace-check",
                "save_annotated": "false",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(create_response.status_code, 202)
        payload = create_response.get_json()
        self.assertEqual(payload["correlation_id"], "campaign-trace-123")
        self.assertEqual(create_response.headers["X-Correlation-ID"], "campaign-trace-123")

        status_response = self.client.get(f"/analysis-jobs/{payload['job_id']}")
        self.assertEqual(status_response.get_json()["correlation_id"], "campaign-trace-123")

    def test_completed_job_can_be_loaded_after_module_reload(self):
        with mock.patch.object(self.app_module, "analyze_with_gpt", return_value=None), mock.patch.object(
            self.worker_module, "analyze_with_gpt", return_value=None
        ):
            create_response = self.client.post(
                "/analysis-jobs",
                data={
                    "video": (BytesIO(b"video-bytes"), "traffic.mp4"),
                    "analysis_name": "restart-check",
                    "save_annotated": "false",
                },
                content_type="multipart/form-data",
            )

            job_id = create_response.get_json()["job_id"]
            processed_job = self.worker_module.process_next_job()
            self.assertIsNotNone(processed_job)
            self.assertEqual(processed_job.job_id, job_id)

        sys.modules.pop("app", None)
        sys.modules.pop("worker", None)
        reloaded_app_module = importlib.import_module("app")
        reloaded_app_module.app.config["TESTING"] = True
        reloaded_client = reloaded_app_module.app.test_client()

        status_response = reloaded_client.get(f"/analysis-jobs/{job_id}")
        self.assertEqual(status_response.status_code, 200)
        payload = status_response.get_json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["analysis_name"], "restart-check")

    def test_cancel_can_stop_a_queued_job_before_worker_claims_it(self):
        create_response = self.client.post(
            "/analysis-jobs",
            data={
                "video": (BytesIO(b"video-bytes"), "traffic.mp4"),
                "analysis_name": "queued-cancel",
                "save_annotated": "false",
            },
            content_type="multipart/form-data",
        )

        job_id = create_response.get_json()["job_id"]
        cancel_response = self.client.post(f"/analysis-jobs/{job_id}/cancel")

        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = cancel_response.get_json()
        self.assertEqual(cancel_payload["status"], "canceled")

        status_response = self.client.get(f"/analysis-jobs/{job_id}")
        self.assertEqual(status_response.status_code, 200)
        payload = status_response.get_json()
        self.assertEqual(payload["status"], "canceled")
        self.assertTrue(payload["cancel_requested"])

        processed_job = self.worker_module.process_next_job()
        self.assertIsNone(processed_job)

    def test_job_stats_report_queue_health_and_worker_counts(self):
        now = self.app_module._utcnow()
        expired = now - datetime.timedelta(minutes=1)
        future = now + datetime.timedelta(minutes=1)

        with self.app_module.app.app_context():
            jobs = [
                self.app_module.AnalysisJob(
                    job_id="queued-job",
                    status="queued",
                    analysis_name="queued",
                    input_path="camera://queued",
                    source_kind="camera_url",
                    save_annotated=False,
                    progress_percent=0,
                    progress_message="Queued for analysis.",
                    created_at=now,
                    updated_at=now,
                ),
                self.app_module.AnalysisJob(
                    job_id="running-job",
                    status="running",
                    analysis_name="running",
                    input_path="camera://running",
                    source_kind="camera_url",
                    save_annotated=False,
                    progress_percent=45,
                    progress_message="Processing",
                    worker_id="worker-a",
                    heartbeat_at=now,
                    lease_expires_at=future,
                    created_at=now,
                    updated_at=now,
                ),
                self.app_module.AnalysisJob(
                    job_id="stale-job",
                    status="running",
                    analysis_name="stale",
                    input_path="camera://stale",
                    source_kind="camera_url",
                    save_annotated=False,
                    progress_percent=45,
                    progress_message="Stale",
                    worker_id="worker-b",
                    heartbeat_at=expired,
                    lease_expires_at=expired,
                    created_at=now,
                    updated_at=now,
                ),
                self.app_module.AnalysisJob(
                    job_id="failed-job",
                    status="failed",
                    analysis_name="failed",
                    input_path="camera://failed",
                    source_kind="camera_url",
                    save_annotated=False,
                    progress_percent=80,
                    progress_message="Failed",
                    error="boom",
                    created_at=now,
                    updated_at=now,
                ),
            ]
            self.app_module.db.session.add_all(jobs)
            self.app_module.db.session.commit()

        response = self.client.get("/analysis-jobs/stats")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["queue_depth"], 1)
        self.assertEqual(payload["stale_leases"], 1)
        self.assertEqual(payload["active_workers"], 1)
        self.assertEqual(payload["status_counts"]["queued"], 1)
        self.assertEqual(payload["status_counts"]["running"], 2)
        self.assertEqual(payload["status_counts"]["failed"], 1)

    def test_retry_endpoint_requeues_failed_camera_job(self):
        now = self.app_module._utcnow()
        with self.app_module.app.app_context():
            job = self.app_module.AnalysisJob(
                job_id="retry-job",
                status="failed",
                analysis_name="retryable",
                input_path="camera://retry",
                source_kind="camera_url",
                save_annotated=False,
                cancel_requested=True,
                progress_percent=100,
                progress_message="Failed",
                error="boom",
                result_json='{"partial": true}',
                worker_id="worker-old",
                heartbeat_at=now,
                lease_expires_at=now,
                created_at=now,
                updated_at=now,
                started_at=now,
                completed_at=now,
            )
            self.app_module.db.session.add(job)
            self.app_module.db.session.commit()

        retry_response = self.client.post("/analysis-jobs/retry-job/retry")

        self.assertEqual(retry_response.status_code, 200)
        payload = retry_response.get_json()
        self.assertEqual(payload["status"], "queued")
        self.assertFalse(payload["cancel_requested"])
        self.assertEqual(payload["progress_percent"], 0)
        self.assertEqual(payload["retry_count"], 1)
        self.assertIsNotNone(payload["last_retried_at"])
        self.assertNotIn("error", payload)
        self.assertNotIn("result", payload)

        with mock.patch.object(self.app_module, "analyze_with_gpt", return_value=None), mock.patch.object(
            self.worker_module, "analyze_with_gpt", return_value=None
        ):
            processed_job = self.worker_module.process_next_job()

        self.assertIsNotNone(processed_job)
        self.assertEqual(processed_job.job_id, "retry-job")

    def test_recent_failures_endpoint_returns_failure_reasons(self):
        now = self.app_module._utcnow()
        with self.app_module.app.app_context():
            self.app_module.db.session.add_all(
                [
                    self.app_module.AnalysisJob(
                        job_id="failed-timeout",
                        correlation_id="trace-timeout",
                        status="failed",
                        analysis_name="timeout",
                        input_path="camera://timeout",
                        source_kind="camera_url",
                        save_annotated=False,
                        error="Analysis timed out.",
                        retry_count=2,
                        created_at=now - datetime.timedelta(minutes=3),
                        updated_at=now - datetime.timedelta(minutes=2),
                        completed_at=now - datetime.timedelta(minutes=2),
                    ),
                    self.app_module.AnalysisJob(
                        job_id="failed-source",
                        status="failed",
                        analysis_name="source",
                        input_path="camera://source",
                        source_kind="camera_url",
                        save_annotated=False,
                        error="Cannot open video source",
                        retry_count=0,
                        created_at=now - datetime.timedelta(minutes=2),
                        updated_at=now - datetime.timedelta(minutes=1),
                        completed_at=now - datetime.timedelta(minutes=1),
                    ),
                ]
            )
            self.app_module.db.session.commit()

        response = self.client.get("/analysis-jobs/failures?limit=1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["failures"][0]["job_id"], "failed-source")
        self.assertEqual(payload["failures"][0]["failure_reason"], "source_unavailable")

    def test_active_workers_endpoint_returns_worker_details(self):
        now = self.app_module._utcnow()
        future = now + datetime.timedelta(minutes=2)
        with self.app_module.app.app_context():
            self.app_module.db.session.add_all(
                [
                    self.app_module.AnalysisJob(
                        job_id="worker-job-a",
                        status="running",
                        analysis_name="worker-a",
                        input_path="camera://worker-a",
                        source_kind="camera_url",
                        save_annotated=False,
                        progress_percent=45,
                        progress_message="Processing",
                        worker_id="worker-1",
                        heartbeat_at=now,
                        lease_expires_at=future,
                        created_at=now,
                        updated_at=now,
                    ),
                    self.app_module.AnalysisJob(
                        job_id="worker-job-b",
                        status="canceling",
                        analysis_name="worker-b",
                        input_path="camera://worker-b",
                        source_kind="camera_url",
                        save_annotated=False,
                        progress_percent=55,
                        progress_message="Canceling",
                        worker_id="worker-1",
                        heartbeat_at=now,
                        lease_expires_at=future,
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )
            self.app_module.db.session.commit()

        response = self.client.get("/analysis-jobs/workers")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["workers"][0]["worker_id"], "worker-1")
        self.assertEqual(payload["workers"][0]["active_job_count"], 2)
        self.assertEqual(
            {job["job_id"] for job in payload["workers"][0]["jobs"]},
            {"worker-job-a", "worker-job-b"},
        )

    def test_job_list_endpoint_supports_status_filter_and_limit(self):
        now = self.app_module._utcnow()
        with self.app_module.app.app_context():
            jobs = [
                self.app_module.AnalysisJob(
                    job_id="queued-1",
                    status="queued",
                    analysis_name="Queued One",
                    input_path="camera://one",
                    source_kind="camera_url",
                    save_annotated=False,
                    created_at=now - datetime.timedelta(minutes=3),
                    updated_at=now - datetime.timedelta(minutes=3),
                ),
                self.app_module.AnalysisJob(
                    job_id="queued-2",
                    status="queued",
                    analysis_name="Queued Two",
                    input_path="camera://two",
                    source_kind="camera_url",
                    save_annotated=False,
                    created_at=now - datetime.timedelta(minutes=2),
                    updated_at=now - datetime.timedelta(minutes=2),
                ),
                self.app_module.AnalysisJob(
                    job_id="completed-1",
                    status="completed",
                    analysis_name="Done",
                    input_path="camera://done",
                    source_kind="camera_url",
                    save_annotated=False,
                    created_at=now - datetime.timedelta(minutes=1),
                    updated_at=now - datetime.timedelta(minutes=1),
                    completed_at=now - datetime.timedelta(minutes=1),
                ),
            ]
            self.app_module.db.session.add_all(jobs)
            self.app_module.db.session.commit()

        response = self.client.get("/analysis-jobs?status=queued&limit=1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["jobs"]), 1)
        self.assertEqual(payload["jobs"][0]["job_id"], "queued-2")
        self.assertEqual(payload["jobs"][0]["status"], "queued")

    def test_job_list_endpoint_supports_offset_source_kind_and_name_filtering(self):
        now = self.app_module._utcnow()
        with self.app_module.app.app_context():
            jobs = [
                self.app_module.AnalysisJob(
                    job_id="morning-cam-1",
                    status="queued",
                    analysis_name="Morning Commute A",
                    input_path="camera://one",
                    source_kind="camera_url",
                    save_annotated=False,
                    created_at=now - datetime.timedelta(minutes=4),
                    updated_at=now - datetime.timedelta(minutes=4),
                ),
                self.app_module.AnalysisJob(
                    job_id="morning-cam-2",
                    status="queued",
                    analysis_name="Morning Commute B",
                    input_path="camera://two",
                    source_kind="camera_url",
                    save_annotated=False,
                    created_at=now - datetime.timedelta(minutes=3),
                    updated_at=now - datetime.timedelta(minutes=3),
                ),
                self.app_module.AnalysisJob(
                    job_id="morning-upload",
                    status="queued",
                    analysis_name="Morning Upload",
                    input_path="upload.mp4",
                    source_kind="upload",
                    save_annotated=False,
                    created_at=now - datetime.timedelta(minutes=2),
                    updated_at=now - datetime.timedelta(minutes=2),
                ),
            ]
            self.app_module.db.session.add_all(jobs)
            self.app_module.db.session.commit()

        response = self.client.get("/analysis-jobs?status=queued&source_kind=camera_url&analysis_name=Morning%20Commute&limit=1&offset=1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["offset"], 1)
        self.assertEqual(payload["jobs"][0]["job_id"], "morning-cam-1")
        self.assertEqual(payload["filters"]["source_kind"], "camera_url")

    def test_history_endpoint_supports_paginated_filtered_shape_when_querying(self):
        now = self.app_module._utcnow()
        with self.app_module.app.app_context():
            records = [
                self.app_module.AnalysisResult(
                    counts=json.dumps({"Commercial Vehicles": 1}),
                    peak_hour=8,
                    peak_count=3,
                    recommendations=json.dumps(["A"]),
                    analysis_name="weekday-am-1",
                    timestamp=now - datetime.timedelta(days=2),
                ),
                self.app_module.AnalysisResult(
                    counts=json.dumps({"Commercial Vehicles": 2}),
                    peak_hour=9,
                    peak_count=4,
                    recommendations=json.dumps(["B"]),
                    analysis_name="weekday-am-2",
                    timestamp=now - datetime.timedelta(days=1),
                ),
                self.app_module.AnalysisResult(
                    counts=json.dumps({"Commercial Vehicles": 5}),
                    peak_hour=10,
                    peak_count=7,
                    recommendations=json.dumps(["C"]),
                    analysis_name="weekend",
                    timestamp=now,
                ),
            ]
            self.app_module.db.session.add_all(records)
            self.app_module.db.session.commit()

        response = self.client.get("/history?analysis_name=weekday&limit=1&offset=1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["offset"], 1)
        self.assertEqual(payload["records"][0]["analysis_name"], "weekday-am-1")
        self.assertEqual(payload["filters"]["analysis_name"], "weekday")

    def test_prune_endpoint_deletes_old_terminal_jobs_and_output_files(self):
        output_dir = Path(os.environ["TVA_OUTPUT_FOLDER"])
        output_dir.mkdir(parents=True, exist_ok=True)
        old_video = output_dir / "old-analysis.mp4"
        fresh_video = output_dir / "fresh-analysis.mp4"
        old_video.write_bytes(b"old")
        fresh_video.write_bytes(b"fresh")

        now = self.app_module._utcnow()
        old_completed_at = now - datetime.timedelta(hours=72)
        fresh_completed_at = now - datetime.timedelta(hours=2)

        with self.app_module.app.app_context():
            jobs = [
                self.app_module.AnalysisJob(
                    job_id="old-job",
                    status="completed",
                    analysis_name="old",
                    input_path="camera://old",
                    source_kind="camera_url",
                    save_annotated=True,
                    result_json=json.dumps({"annotated_video": old_video.name}),
                    created_at=old_completed_at,
                    updated_at=old_completed_at,
                    completed_at=old_completed_at,
                ),
                self.app_module.AnalysisJob(
                    job_id="fresh-job",
                    status="completed",
                    analysis_name="fresh",
                    input_path="camera://fresh",
                    source_kind="camera_url",
                    save_annotated=True,
                    result_json=json.dumps({"annotated_video": fresh_video.name}),
                    created_at=fresh_completed_at,
                    updated_at=fresh_completed_at,
                    completed_at=fresh_completed_at,
                ),
            ]
            self.app_module.db.session.add_all(jobs)
            self.app_module.db.session.commit()

        response = self.client.post("/analysis-jobs/prune", json={"retention_hours": 24})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["deleted_jobs"], 1)
        self.assertEqual(payload["deleted_output_files"], 1)

        with self.app_module.app.app_context():
            self.assertIsNone(self.app_module.db.session.get(self.app_module.AnalysisJob, "old-job"))
            self.assertIsNotNone(self.app_module.db.session.get(self.app_module.AnalysisJob, "fresh-job"))

        self.assertFalse(old_video.exists())
        self.assertTrue(fresh_video.exists())

    def test_health_reports_database_and_job_snapshot(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["database"], "ok")
        self.assertIn("jobs", payload)
        self.assertIn("status_counts", payload["jobs"])

    def test_debug_routes_are_not_exposed_by_default(self):
        self.assertEqual(self.client.post("/test_analysis", json={}).status_code, 404)
        self.assertEqual(self.client.get("/test_gpt_analysis").status_code, 404)

    def test_metrics_exports_prometheus_queue_and_history_values(self):
        now = self.app_module._utcnow()
        with self.app_module.app.app_context():
            self.app_module.db.session.add(
                self.app_module.AnalysisJob(
                    job_id="queued-metric-job",
                    status="queued",
                    analysis_name="queued-metric",
                    input_path="camera://metric",
                    source_kind="camera_url",
                    save_annotated=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            self.app_module.db.session.add(
                self.app_module.AnalysisResult(
                    counts=json.dumps({"Commercial Vehicles": 1}),
                    peak_hour=9,
                    peak_count=1,
                    recommendations=json.dumps(["test"]),
                    analysis_name="metric-history",
                    timestamp=now,
                )
            )
            self.app_module.db.session.commit()

        response = self.client.get("/metrics")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.content_type)
        body = response.get_data(as_text=True)
        self.assertIn("traffic_video_analysis_jobs_total{status=\"queued\"} 1", body)
        self.assertIn("traffic_video_analysis_queue_depth 1", body)
        self.assertIn("traffic_video_analysis_history_records_total 1", body)

    def test_metrics_exports_duration_and_failure_breakdown(self):
        now = self.app_module._utcnow()
        with self.app_module.app.app_context():
            self.app_module.db.session.add_all(
                [
                    self.app_module.AnalysisJob(
                        job_id="completed-duration",
                        status="completed",
                        analysis_name="completed-duration",
                        input_path="camera://done",
                        source_kind="camera_url",
                        save_annotated=False,
                        created_at=now - datetime.timedelta(seconds=80),
                        updated_at=now,
                        started_at=now - datetime.timedelta(seconds=60),
                        completed_at=now,
                    ),
                    self.app_module.AnalysisJob(
                        job_id="failed-timeout",
                        status="failed",
                        analysis_name="failed-timeout",
                        input_path="camera://timeout",
                        source_kind="camera_url",
                        save_annotated=False,
                        error="Analysis timed out.",
                        retry_count=2,
                        created_at=now - datetime.timedelta(seconds=40),
                        updated_at=now,
                        started_at=now - datetime.timedelta(seconds=30),
                        completed_at=now,
                    ),
                ]
            )
            self.app_module.db.session.commit()

        response = self.client.get("/metrics")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("traffic_video_analysis_queue_wait_seconds_avg", body)
        self.assertIn("traffic_video_analysis_processing_seconds_avg", body)
        self.assertIn('traffic_video_analysis_failures_total{reason="timeout"} 1', body)
        self.assertIn("traffic_video_analysis_job_retries_total 2", body)

    def test_diagnostics_reports_runtime_configuration_and_paths(self):
        response = self.client.get("/diagnostics")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn(payload["status"], {"ok", "degraded"})
        self.assertIn("configuration", payload)
        self.assertIn("paths", payload)
        self.assertIn("models", payload)
        self.assertTrue(payload["paths"]["upload_folder"]["exists"])
        self.assertTrue(payload["paths"]["output_folder"]["exists"])
        self.assertIn(payload["paths"]["output_folder"]["disk_status"], {"ok", "warning", "critical", "unavailable"})

    def test_async_job_status_returns_404_for_unknown_job(self):
        response = self.client.get("/analysis-jobs/does-not-exist")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error_code"], "job_not_found")

    def test_invalid_limit_returns_standardized_query_error(self):
        response = self.client.get("/analysis-jobs?limit=abc")

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertEqual(payload["error_code"], "invalid_query_parameter")
        self.assertIn("limit", payload["error"])

    def test_app_module_keeps_expected_public_surface_after_refactor(self):
        expected_names = [
            "app",
            "db",
            "AnalysisJob",
            "AnalysisResult",
            "UPLOAD_FOLDER",
            "OUTPUT_FOLDER",
            "_utcnow",
            "_cleanup_uploaded_file",
            "_job_video_source",
            "_persist_analysis_record",
            "_job_stats_snapshot",
            "diagnostics_snapshot",
            "prune_terminal_jobs",
            "execute_analysis",
            "analyze_with_gpt",
            "log_event",
        ]

        for name in expected_names:
            self.assertTrue(hasattr(self.app_module, name), name)


if __name__ == "__main__":
    unittest.main()
