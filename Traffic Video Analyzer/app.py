import importlib
import sys


MODULE_ORDER = [
    "backend.core",
    "backend.models",
    "backend.observability",
    "backend.services",
    "backend.routes",
]

def _clear_modules():
    for module_name in list(sys.modules):
        if module_name == "backend" or module_name.startswith("backend."):
            sys.modules.pop(module_name, None)


_clear_modules()
_loaded_modules = {name: importlib.import_module(name) for name in MODULE_ORDER}

_core = _loaded_modules["backend.core"]
_models = _loaded_modules["backend.models"]
_observability = _loaded_modules["backend.observability"]
_services = _loaded_modules["backend.services"]

app = _core.app
db = _core.db

BASE_DIR = _core.BASE_DIR
INSTANCE_DIR = _core.INSTANCE_DIR
UPLOAD_FOLDER = _core.UPLOAD_FOLDER
OUTPUT_FOLDER = _core.OUTPUT_FOLDER
DEFAULT_DB_PATH = _core.DEFAULT_DB_PATH
DEFAULT_JOB_RETENTION_HOURS = _core.DEFAULT_JOB_RETENTION_HOURS
TERMINAL_JOB_STATUSES = _core.TERMINAL_JOB_STATUSES
DEFAULT_MAX_UPLOAD_BYTES = _core.DEFAULT_MAX_UPLOAD_BYTES
ALLOWED_VIDEO_EXTENSIONS = _core.ALLOWED_VIDEO_EXTENSIONS
ALLOWED_CAMERA_URL_SCHEMES = _core.ALLOWED_CAMERA_URL_SCHEMES
TEST_ROUTES_ENABLED = _core.TEST_ROUTES_ENABLED

_resolve_path = _core._resolve_path
_is_truthy = _core._is_truthy
_utcnow = _core._utcnow
_to_iso = _core._to_iso
_file_extension = _core._file_extension

AnalysisJob = _models.AnalysisJob
AnalysisResult = _models.AnalysisResult
initialize_database = _models.initialize_database

log_event = _observability.log_event
_job_stats_snapshot = _observability._job_stats_snapshot
_metrics_snapshot = _observability._metrics_snapshot
_prometheus_metrics_text = _observability._prometheus_metrics_text
diagnostics_snapshot = _observability.diagnostics_snapshot

run_video_pipeline = _services.run_video_pipeline
run_local_analysis = _services.run_local_analysis
_cleanup_uploaded_file = _services._cleanup_uploaded_file
_persist_analysis_record = _services._persist_analysis_record
_job_video_source = _services._job_video_source
prune_terminal_jobs = _services.prune_terminal_jobs
execute_analysis = _services.execute_analysis
analyze_with_gpt = _services.analyze_with_gpt


if __name__ == "__main__":
    app.run(debug=False, threaded=True)
