import datetime
import os

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy


BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def _resolve_path(env_name, default_name):
    value = os.getenv(env_name, default_name)
    if os.path.isabs(value):
        return value
    return os.path.join(BASE_DIR, value)


def _is_truthy(value):
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


TEST_ROUTES_ENABLED = (
    _is_truthy(os.getenv("TVA_ENABLE_TEST_ROUTES"))
    or os.getenv("TVA_ENV", "").strip().lower() == "development"
    or os.getenv("FLASK_ENV", "").strip().lower() == "development"
)


def _utcnow():
    return datetime.datetime.now(datetime.UTC)


def _to_iso(value):
    return value.isoformat() if value else None


def _file_extension(filename):
    _, extension = os.path.splitext(filename or "")
    return extension.lower().lstrip(".")


def _int_env(name, default):
    raw_value = os.getenv(name)
    if raw_value in {None, ""}:
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _parse_resize_dim(raw_value, default=(512, 384)):
    if raw_value in {None, ""}:
        return default
    normalized = str(raw_value).lower().replace("x", ",")
    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    if len(parts) != 2:
        return default
    try:
        width, height = (int(parts[0]), int(parts[1]))
    except (TypeError, ValueError):
        return default
    if width < 64 or height < 64:
        return default
    return (width, height)


DEFAULT_JOB_RETENTION_HOURS = int(os.getenv("TVA_JOB_RETENTION_HOURS", "168"))
TERMINAL_JOB_STATUSES = ("completed", "failed", "canceled")
DEFAULT_MAX_UPLOAD_BYTES = int(os.getenv("TVA_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024)))
ALLOWED_VIDEO_EXTENSIONS = {
    extension.strip().lower()
    for extension in os.getenv("TVA_ALLOWED_VIDEO_EXTENSIONS", "mp4,mov,avi,mkv,webm,m4v,mpeg,mpg").split(",")
    if extension.strip()
}
ALLOWED_CAMERA_URL_SCHEMES = {
    scheme.strip().lower()
    for scheme in os.getenv("TVA_ALLOWED_CAMERA_SCHEMES", "rtsp,rtsps,http,https").split(",")
    if scheme.strip()
}
DEFAULT_PIPELINE_RESIZE_DIM = _parse_resize_dim(os.getenv("TVA_PIPELINE_RESIZE_DIM"), default=(512, 384))
DEFAULT_PIPELINE_DETECTION_INTERVAL = max(1, _int_env("TVA_PIPELINE_DETECTION_INTERVAL", 2))
DEFAULT_PIPELINE_PROGRESS_REPORT_FRAMES = max(1, _int_env("TVA_PIPELINE_PROGRESS_REPORT_FRAMES", 45))
DEFAULT_PIPELINE_TRACKER_BACKEND = os.getenv("TVA_PIPELINE_TRACKER_BACKEND", "centroid").strip().lower() or "centroid"

INSTANCE_DIR = _resolve_path("TVA_INSTANCE_FOLDER", "instance")
UPLOAD_FOLDER = _resolve_path("TVA_UPLOAD_FOLDER", "uploads")
OUTPUT_FOLDER = _resolve_path("TVA_OUTPUT_FOLDER", "output")
DEFAULT_DB_PATH = os.path.join(INSTANCE_DIR, "analysis_history.db").replace("\\", "/")

os.makedirs(INSTANCE_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("TVA_DATABASE_URI", f"sqlite:///{DEFAULT_DB_PATH}")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = DEFAULT_MAX_UPLOAD_BYTES

db = SQLAlchemy(app)
