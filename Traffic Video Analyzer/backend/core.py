import datetime
import os

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine


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


def _float_env(name, default):
    raw_value = os.getenv(name)
    if raw_value in {None, ""}:
        return default
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def _parse_roi_points(raw_value):
    """Parse "x,y;x,y;..." polygon points as fractions of frame width/height."""
    if not raw_value or not raw_value.strip():
        return None
    points = []
    for chunk in raw_value.split(";"):
        if not chunk.strip():
            continue
        parts = [part.strip() for part in chunk.split(",") if part.strip()]
        if len(parts) != 2:
            return None
        try:
            x, y = float(parts[0]), float(parts[1])
        except ValueError:
            return None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return None
        points.append((x, y))
    return points if len(points) >= 3 else None


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
# bytetrack measured 94.7% macro counting accuracy vs centroid's 88.4% at
# native resolution on the labeled reference clips (2026-06-28).
DEFAULT_PIPELINE_TRACKER_BACKEND = os.getenv("TVA_PIPELINE_TRACKER_BACKEND", "bytetrack").strip().lower() or "bytetrack"
DEFAULT_PIPELINE_CLASSIFICATION_VOTE_SAMPLES = max(1, _int_env("TVA_PIPELINE_CLASSIFICATION_VOTE_SAMPLES", 3))
# 0.5 is the value the original methodology report specifies and evaluated with.
DEFAULT_PIPELINE_CONFIDENCE_THRESHOLD = min(1.0, max(0.0, _float_env("TVA_PIPELINE_CONFIDENCE_THRESHOLD", 0.5)))
DEFAULT_PIPELINE_NMS_IOU = min(1.0, max(0.0, _float_env("TVA_PIPELINE_NMS_IOU", 0.7)))
# Detection floor fed to ByteTrack/BoT-SORT. Lower values bridge occlusion
# dips but flood dense junctions with noise tracks; 0.5 measured best macro
# accuracy on the reference clips (0.25/0.1 helped sparse cam1, hurt cam2).
DEFAULT_PIPELINE_TRACK_CONF = min(1.0, max(0.0, _float_env("TVA_PIPELINE_TRACK_CONF", 0.5)))
DEFAULT_PIPELINE_CLASSIFICATION_THRESHOLD = min(1.0, max(0.0, _float_env("TVA_PIPELINE_CLASSIFICATION_THRESHOLD", 0.4)))
DEFAULT_PIPELINE_MIN_CROP = max(1, _int_env("TVA_PIPELINE_MIN_CROP", 10))
DEFAULT_PIPELINE_IMGSZ = max(64, _int_env("TVA_PIPELINE_IMGSZ", 640))
_RAW_ROI_POINTS = os.getenv("TVA_PIPELINE_ROI_POINTS")
DEFAULT_PIPELINE_ROI_POINTS = _parse_roi_points(_RAW_ROI_POINTS)
if _RAW_ROI_POINTS and _RAW_ROI_POINTS.strip() and DEFAULT_PIPELINE_ROI_POINTS is None:
    print(f"Warning: invalid TVA_PIPELINE_ROI_POINTS {_RAW_ROI_POINTS!r}; falling back to the default center ROI.")
DEFAULT_PIPELINE_MODEL_PATH = os.getenv("TVA_PIPELINE_MODEL_PATH", "yolo11n.pt").strip() or "yolo11n.pt"
DEFAULT_PIPELINE_CLASSIFIER_PATH = os.getenv("TVA_PIPELINE_CLASSIFIER_PATH", "mobilenetv3_original.keras").strip() or "mobilenetv3_original.keras"
# Mirrors the DeepSORT n_init=2 the original report validated counting with.
DEFAULT_PIPELINE_TRACKER_MIN_HITS = max(1, _int_env("TVA_PIPELINE_TRACKER_MIN_HITS", 2))

INSTANCE_DIR = _resolve_path("TVA_INSTANCE_FOLDER", "instance")
UPLOAD_FOLDER = _resolve_path("TVA_UPLOAD_FOLDER", "uploads")
OUTPUT_FOLDER = _resolve_path("TVA_OUTPUT_FOLDER", "output")
DEFAULT_DB_PATH = os.path.join(INSTANCE_DIR, "analysis_history.db").replace("\\", "/")

os.makedirs(INSTANCE_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

SQLITE_BUSY_TIMEOUT_MS = max(0, _int_env("TVA_SQLITE_BUSY_TIMEOUT_MS", 5000))


@event.listens_for(Engine, "connect")
def _configure_sqlite_connection(dbapi_connection, connection_record):
    """Enable WAL + a busy timeout on every SQLite connection.

    The API and worker run as separate processes against one SQLite file and
    commit frequently (progress heartbeats, job state). The default rollback
    journal takes a database-level write lock, so concurrent writers raise
    "database is locked". WAL lets readers and a single writer coexist, and the
    busy timeout makes a contending writer wait instead of failing immediately.
    Guarded to SQLite so a Postgres TVA_DATABASE_URI is unaffected.
    """
    if type(dbapi_connection).__module__.split(".")[0] not in {"sqlite3", "pysqlite2"}:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("TVA_DATABASE_URI", f"sqlite:///{DEFAULT_DB_PATH}")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = DEFAULT_MAX_UPLOAD_BYTES

db = SQLAlchemy(app)
