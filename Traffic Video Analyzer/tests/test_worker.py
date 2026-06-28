import importlib
import datetime
import os
import shutil
import sys
import time
import types
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def fake_process_video(video_path, start_dt=None, save_annotated=False, analysis_name=None, **kwargs):
    return {
        "counts": {
            "Commercial Vehicles": 4,
            "High-End Vehicles": 0,
            "Low-End Vehicles": 0,
            "Mid-Range Vehicles": 1,
            "Motorcycle": 0,
            "Unclassified": 0,
        },
        "time_series": [
            {
                "timestamp": "2024-07-07 08:00:00",
                "Commercial Vehicles": 1,
                "High-End Vehicles": 0,
                "Low-End Vehicles": 0,
                "Mid-Range Vehicles": 0,
                "Motorcycle": 0,
                "Unclassified": 0,
            },
            {
                "timestamp": "2024-07-07 08:05:00",
                "Commercial Vehicles": 4,
                "High-End Vehicles": 0,
                "Low-End Vehicles": 0,
                "Mid-Range Vehicles": 1,
                "Motorcycle": 0,
                "Unclassified": 0,
            },
        ],
        "annotated_video": None,
    }


class WorkerTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / "tests_artifacts"
        temp_root.mkdir(exist_ok=True)
        self.temp_path = temp_root / f"worker_{uuid.uuid4().hex}"
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
            "peak": {"hour": 8, "count": 5},
            "recommendations": ["Morning commuters respond well to convenience ads."],
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

    def tearDown(self):
        for key in ["TVA_DATABASE_URI", "TVA_UPLOAD_FOLDER", "TVA_OUTPUT_FOLDER", "TVA_DISABLE_GPT"]:
            os.environ.pop(key, None)
        sys.modules.pop("app", None)
        sys.modules.pop("worker", None)

    def test_process_next_job_claims_one_job_and_completes_it(self):
        with self.app_module.app.app_context():
            first = self.app_module.AnalysisJob(
                job_id="job-a",
                status="queued",
                analysis_name="first",
                correlation_id="trace-job-a",
                input_path="camera-1",
                source_kind="camera_url",
                save_annotated=False,
                progress_percent=0,
                progress_message="Queued for analysis.",
                start_dt=self.app_module._utcnow(),
                created_at=self.app_module._utcnow(),
                updated_at=self.app_module._utcnow(),
            )
            second = self.app_module.AnalysisJob(
                job_id="job-b",
                status="queued",
                analysis_name="second",
                input_path="camera-2",
                source_kind="camera_url",
                save_annotated=False,
                progress_percent=0,
                progress_message="Queued for analysis.",
                start_dt=self.app_module._utcnow(),
                created_at=self.app_module._utcnow(),
                updated_at=self.app_module._utcnow(),
            )
            self.app_module.db.session.add_all([first, second])
            self.app_module.db.session.commit()

        with mock.patch.object(self.app_module, "analyze_with_gpt", return_value=None), mock.patch.object(
            self.worker_module, "analyze_with_gpt", return_value=None
        ), mock.patch.object(self.worker_module.app.logger, "info") as info_log:
            processed_job = self.worker_module.process_next_job()

        self.assertIsNotNone(processed_job)
        self.assertEqual(processed_job.job_id, "job-a")
        logged_messages = [call.args[0] for call in info_log.call_args_list]
        self.assertTrue(any('"event":"analysis_job_claimed"' in message for message in logged_messages))
        self.assertTrue(any('"event":"analysis_job_completed"' in message for message in logged_messages))
        completion_logs = [message for message in logged_messages if '"event":"analysis_job_completed"' in message]
        self.assertIn('"correlation_id":"trace-job-a"', completion_logs[0])
        self.assertIn('"processing_seconds"', completion_logs[0])

        with self.app_module.app.app_context():
            completed = self.app_module.db.session.get(self.app_module.AnalysisJob, "job-a")
            queued = self.app_module.db.session.get(self.app_module.AnalysisJob, "job-b")
            self.assertEqual(completed.status, "completed")
            self.assertEqual(completed.progress_percent, 100)
            self.assertIsNotNone(completed.result_json)
            self.assertEqual(queued.status, "queued")

    def test_claim_next_job_sets_worker_lease_and_prevents_second_claim(self):
        with self.app_module.app.app_context():
            queued = self.app_module.AnalysisJob(
                job_id="lease-job",
                status="queued",
                analysis_name="lease-check",
                input_path="camera-1",
                source_kind="camera_url",
                save_annotated=False,
                progress_percent=0,
                progress_message="Queued for analysis.",
                start_dt=self.app_module._utcnow(),
                created_at=self.app_module._utcnow(),
                updated_at=self.app_module._utcnow(),
            )
            self.app_module.db.session.add(queued)
            self.app_module.db.session.commit()

        claimed = self.worker_module.claim_next_job(worker_id="worker-a")
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.job_id, "lease-job")

        second_claim = self.worker_module.claim_next_job(worker_id="worker-b")
        self.assertIsNone(second_claim)

        with self.app_module.app.app_context():
            job = self.app_module.db.session.get(self.app_module.AnalysisJob, "lease-job")
            self.assertEqual(job.status, "running")
            self.assertEqual(job.worker_id, "worker-a")
            self.assertIsNotNone(job.lease_expires_at)

    def test_expired_running_job_can_be_reclaimed_by_another_worker(self):
        expired_time = self.app_module._utcnow() - datetime.timedelta(seconds=10)
        with self.app_module.app.app_context():
            stale = self.app_module.AnalysisJob(
                job_id="stale-job",
                status="running",
                analysis_name="stale-check",
                input_path="camera-1",
                source_kind="camera_url",
                save_annotated=False,
                progress_percent=25,
                progress_message="Old worker stopped heartbeating.",
                start_dt=self.app_module._utcnow(),
                created_at=self.app_module._utcnow(),
                updated_at=self.app_module._utcnow(),
                started_at=self.app_module._utcnow(),
                worker_id="worker-old",
                lease_expires_at=expired_time,
            )
            self.app_module.db.session.add(stale)
            self.app_module.db.session.commit()

        claimed = self.worker_module.claim_next_job(worker_id="worker-new")
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.job_id, "stale-job")

        with self.app_module.app.app_context():
            job = self.app_module.db.session.get(self.app_module.AnalysisJob, "stale-job")
            self.assertEqual(job.status, "running")
            self.assertEqual(job.worker_id, "worker-new")
            self.assertIsNotNone(job.lease_expires_at)
            self.assertGreater(job.lease_expires_at, expired_time.replace(tzinfo=None))

    def test_process_job_marks_timed_out_analysis_as_failed(self):
        old_start = self.app_module._utcnow() - datetime.timedelta(hours=3)
        with self.app_module.app.app_context():
            job = self.app_module.AnalysisJob(
                job_id="timed-out-job",
                status="running",
                analysis_name="timeout-check",
                input_path="camera-1",
                source_kind="camera_url",
                save_annotated=False,
                progress_percent=10,
                progress_message="Still running",
                start_dt=old_start,
                created_at=old_start,
                updated_at=old_start,
                started_at=old_start,
                worker_id="worker-a",
                heartbeat_at=self.app_module._utcnow(),
                lease_expires_at=self.app_module._utcnow() + datetime.timedelta(minutes=1),
            )
            self.app_module.db.session.add(job)
            self.app_module.db.session.commit()

        class AnalysisCancelled(RuntimeError):
            pass

        def fake_execute_analysis(**kwargs):
            self.assertTrue(kwargs["should_cancel"]())
            raise AnalysisCancelled("timed out")

        with mock.patch.object(self.worker_module, "execute_analysis", side_effect=fake_execute_analysis):
            processed_job = self.worker_module.process_job("timed-out-job", worker_id="worker-a")

        self.assertIsNotNone(processed_job)
        with self.app_module.app.app_context():
            timed_out = self.app_module.db.session.get(self.app_module.AnalysisJob, "timed-out-job")
            self.assertEqual(timed_out.status, "failed")
            self.assertEqual(timed_out.error, "Analysis timed out.")

    def test_process_job_handles_naive_db_timestamps_during_progress_refresh(self):
        now = datetime.datetime.utcnow()
        with self.app_module.app.app_context():
            job = self.app_module.AnalysisJob(
                job_id="naive-progress-job",
                status="running",
                analysis_name="naive-check",
                input_path="camera-1",
                source_kind="camera_url",
                save_annotated=False,
                progress_percent=10,
                progress_message="Still running",
                start_dt=now,
                created_at=now,
                updated_at=now,
                started_at=now,
                worker_id="worker-a",
                heartbeat_at=now,
                lease_expires_at=now + datetime.timedelta(seconds=15),
            )
            self.app_module.db.session.add(job)
            self.app_module.db.session.commit()

        def fake_execute_analysis(**kwargs):
            kwargs["progress_callback"](15, "Processed 15 frames.")
            return {
                "counts": {
                    "Commercial Vehicles": 1,
                    "High-End Vehicles": 0,
                    "Low-End Vehicles": 0,
                    "Mid-Range Vehicles": 0,
                    "Motorcycle": 0,
                    "Unclassified": 0,
                },
                "time_series": [
                    {
                        "timestamp": "2024-07-07 08:00:00",
                        "Commercial Vehicles": 1,
                        "High-End Vehicles": 0,
                        "Low-End Vehicles": 0,
                        "Mid-Range Vehicles": 0,
                        "Motorcycle": 0,
                        "Unclassified": 0,
                    }
                ],
                "peak": {"hour": 8, "count": 1},
                "recommendations": ["test"],
                "analysis_name": "naive-check",
            }

        with mock.patch.object(self.worker_module, "execute_analysis", side_effect=fake_execute_analysis):
            processed_job = self.worker_module.process_job("naive-progress-job", worker_id="worker-a")

        self.assertIsNotNone(processed_job)
        with self.app_module.app.app_context():
            completed = self.app_module.db.session.get(self.app_module.AnalysisJob, "naive-progress-job")
            self.assertEqual(completed.status, "completed")
            self.assertGreaterEqual(completed.progress_percent, 15)

    def test_process_job_refreshes_lease_while_analysis_has_no_progress_callbacks(self):
        initial_heartbeat = datetime.datetime.utcnow()
        with self.app_module.app.app_context():
            job = self.app_module.AnalysisJob(
                job_id="model-loading-job",
                status="running",
                analysis_name="slow-model-load",
                input_path="camera-1",
                source_kind="camera_url",
                save_annotated=False,
                progress_percent=0,
                progress_message="Starting analysis...",
                start_dt=initial_heartbeat,
                created_at=initial_heartbeat,
                updated_at=initial_heartbeat,
                started_at=initial_heartbeat,
                worker_id="worker-a",
                heartbeat_at=initial_heartbeat,
                lease_expires_at=initial_heartbeat + datetime.timedelta(seconds=30),
            )
            self.app_module.db.session.add(job)
            self.app_module.db.session.commit()

        observed = {"heartbeat_advanced": False}

        def fake_execute_analysis(**kwargs):
            del kwargs
            time.sleep(0.2)
            self.worker_module.db.session.expire_all()
            current = self.worker_module.db.session.get(self.worker_module.AnalysisJob, "model-loading-job")
            observed["heartbeat_advanced"] = current.heartbeat_at > initial_heartbeat
            return {
                "counts": {
                    "Commercial Vehicles": 1,
                    "High-End Vehicles": 0,
                    "Low-End Vehicles": 0,
                    "Mid-Range Vehicles": 0,
                    "Motorcycle": 0,
                    "Unclassified": 0,
                },
                "time_series": [],
                "peak": None,
                "recommendations": [],
                "analysis_name": "slow-model-load",
            }

        with mock.patch.object(
            self.worker_module._runtime,
            "LEASE_HEARTBEAT_INTERVAL_SECONDS",
            0.05,
            create=True,
        ), mock.patch.object(self.worker_module, "execute_analysis", side_effect=fake_execute_analysis):
            self.worker_module.process_job("model-loading-job", worker_id="worker-a")

        self.assertTrue(observed["heartbeat_advanced"])

    def test_worker_that_loses_job_ownership_does_not_delete_upload_or_change_status(self):
        upload_path = self.temp_path / "uploads" / "ownership-check.mp4"
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(b"video")
        now = self.app_module._utcnow()

        with self.app_module.app.app_context():
            job = self.app_module.AnalysisJob(
                job_id="ownership-lost-job",
                status="running",
                analysis_name="ownership-check",
                input_path=str(upload_path),
                source_kind="upload",
                save_annotated=False,
                progress_percent=0,
                progress_message="Starting analysis...",
                start_dt=now,
                created_at=now,
                updated_at=now,
                started_at=now,
                worker_id="worker-a",
                heartbeat_at=now,
                lease_expires_at=now + datetime.timedelta(seconds=30),
            )
            self.app_module.db.session.add(job)
            self.app_module.db.session.commit()

        class AnalysisCancelled(RuntimeError):
            pass

        def fake_execute_analysis(**kwargs):
            del kwargs
            current = self.worker_module.db.session.get(self.worker_module.AnalysisJob, "ownership-lost-job")
            current.worker_id = "worker-b"
            current.status = "running"
            current.progress_message = "Reclaimed by worker-b."
            current.lease_expires_at = self.worker_module._runtime._utcnow() + datetime.timedelta(seconds=30)
            self.worker_module.db.session.commit()
            raise AnalysisCancelled("worker ownership changed")

        with mock.patch.object(self.worker_module, "execute_analysis", side_effect=fake_execute_analysis):
            self.worker_module.process_job("ownership-lost-job", worker_id="worker-a")

        with self.app_module.app.app_context():
            current = self.app_module.db.session.get(self.app_module.AnalysisJob, "ownership-lost-job")
            self.assertEqual(current.status, "running")
            self.assertEqual(current.worker_id, "worker-b")
        self.assertTrue(upload_path.exists())

    def test_maybe_run_maintenance_prunes_when_interval_elapsed(self):
        with mock.patch.object(self.worker_module, "prune_terminal_jobs", return_value={"deleted_jobs": 1}) as prune_jobs:
            first_run = self.worker_module.maybe_run_maintenance(now=self.app_module._utcnow(), force=True)
            second_run = self.worker_module.maybe_run_maintenance(now=self.app_module._utcnow())

        self.assertTrue(first_run)
        self.assertFalse(second_run)
        self.assertEqual(prune_jobs.call_count, 1)

    def test_log_worker_startup_emits_diagnostics_summary(self):
        with mock.patch.object(self.worker_module.app.logger, "info") as info_log:
            self.worker_module.log_worker_startup(worker_id="worker-startup")

        logged_messages = [call.args[0] for call in info_log.call_args_list]
        startup_logs = [message for message in logged_messages if '"event":"worker_startup"' in message]
        self.assertEqual(len(startup_logs), 1)
        self.assertIn('"worker_id":"worker-startup"', startup_logs[0])
        self.assertIn('"diagnostics_status"', startup_logs[0])
        self.assertIn('"pipeline_tracker_backend"', startup_logs[0])

    def test_worker_module_keeps_expected_public_surface_after_refactor(self):
        expected_names = [
            "get_worker_id",
            "recover_abandoned_jobs",
            "claim_next_job",
            "process_job",
            "process_next_job",
            "run_worker_loop",
            "maybe_run_maintenance",
            "log_worker_startup",
            "prune_terminal_jobs",
            "execute_analysis",
            "AnalysisJob",
            "app",
            "db",
        ]

        for name in expected_names:
            self.assertTrue(hasattr(self.worker_module, name), name)


if __name__ == "__main__":
    unittest.main()
