# Traffic Video Analyzer

Traffic Video Analyzer is a web application for turning roadside traffic footage into billboard planning data. Users upload a video or submit a supported camera stream, then the system detects vehicles, tracks them, classifies them, summarizes the traffic mix, and returns advertising-oriented recommendations.

The current implementation has three runtime processes:

- Vue frontend for uploads, queue monitoring, history, job detail, and results review
- Flask API for validation, job management, history, metrics, and output serving
- Python worker for video processing, cancellation, retry recovery, and maintenance

---

## Quick Start

Open three terminals from the project root unless noted otherwise.

### 1. Install Backend Dependencies

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

GPT recommendations are optional. Without an API key, the app uses local recommendation logic.

Optional `.env`:

```env
OPENAI_API_KEY=your_api_key_here
```

### 2. Install Frontend Dependencies

```powershell
cd vehicle-webapp
npm install
```

### 3. Start The Backend API

```powershell
python app.py
```

Default API URL:

```text
http://localhost:5000
```

### 4. Start The Worker

```powershell
python worker.py
```

The worker may look idle when no jobs are queued. That is normal.

### 5. Start The Frontend

```powershell
cd vehicle-webapp
npm run serve
```

Default frontend URL:

```text
http://localhost:8080
```

---

## Using The App

1. Open `http://localhost:8080`.
2. Choose an input:
   - upload a supported video file
   - enter a numeric webcam index such as `0`
   - enter a direct `rtsp`, `rtsps`, `http`, or `https` camera stream URL
3. Optionally set the video start date, start time, and analysis name.
4. Enable `Save annotated video output for review` if you want a playable annotated result file.
5. Submit the analysis.
6. Monitor progress in the status panel and recent jobs panel.
7. Review the results dashboard, recommendations, annotated video, job details, and history.

YouTube page URLs such as `youtube.com/watch?...` and `youtu.be/...` are intentionally blocked. OpenCV usually cannot read normal YouTube pages as direct video streams.

---

## Architecture

```text
Vue frontend
  -> Flask API
  -> SQLite-backed job queue
  -> Worker process
  -> YOLO detection
  -> Tracker
  -> MobileNetV3 classification
  -> Local analytics and optional GPT recommendations
  -> SQLite history and optional annotated video output
```

Jobs are asynchronous. The frontend creates a job, polls `/analysis-jobs/<job_id>`, and opens the completed result when the worker finishes.

---

## Project Layout

```text
.
|-- app.py                         # Flask API compatibility entrypoint
|-- worker.py                      # Worker compatibility entrypoint
|-- analysis.py                    # Legacy import facade
|-- pipeline.py                    # Legacy import facade
|-- backend/
|   |-- core.py                    # Flask, database, paths, environment defaults
|   |-- models.py                  # SQLAlchemy models and schema compatibility
|   |-- routes.py                  # API routes and request validation
|   |-- services.py                # Analysis orchestration and persistence
|   |-- observability.py           # Structured logs, metrics, diagnostics
|   |-- worker_runtime.py          # Worker loop, leases, cancellation, maintenance
|   `-- inference/
|       |-- pipeline.py            # Video processing pipeline
|       |-- analysis.py            # Local recommendation logic
|       |-- trackers.py            # DeepSORT and centroid tracker backends
|       `-- classification_voting.py
|-- vehicle-webapp/                # Vue frontend
|-- tests/                         # Backend and pipeline regression tests
|-- output/                        # Runtime annotated videos
|-- uploads/                       # Runtime uploaded videos
|-- runtime_logs/                  # Optional local run logs
`-- instance/                      # SQLite database by default
```

Generated runtime folders such as `output/`, `uploads/`, `runtime_logs/`, `instance/`, `tests_artifacts/`, and `__pycache__/` should not be treated as source files.

---

## Current Pipeline Defaults

The pipeline runs inference on native-resolution frames and is tuned from measurements on labeled reference clips:

- YOLO inference resolution: `640` (aspect-preserving letterbox from the native frame)
- YOLO detection interval: every `2` frames
- tracker backend: `bytetrack` (Kalman-based, fused with detection; measured 94.7% macro counting accuracy vs 88.4% for `centroid` at native resolution)
- detection confidence: `0.5`; classification voting samples: `3`
- annotated output canvas: `1280x720` (drawing only, does not affect inference)
- progress database writes: throttled by time and progress delta

Use the counting harness when comparing configurations on real footage (ground truth is parsed from `<N>vehicles` in the filename):

```powershell
venv\Scripts\python.exe evaluate_counting.py --label my-config --tracker bytetrack --conf 0.5
```

To test classification stability across repeated runs:

```powershell
py validate_pipeline_voting.py --video segments_segments_1.mp4 --runs 2 --vote-samples 3
```

---

## API Overview

### Analysis Jobs

- `POST /analysis-jobs`
- `GET /analysis-jobs`
- `GET /analysis-jobs/<job_id>`
- `POST /analysis-jobs/<job_id>/cancel`
- `POST /analysis-jobs/<job_id>/retry`
- `POST /analysis-jobs/prune`

`GET /analysis-jobs` supports:

- `status`
- `source_kind`
- `analysis_name`
- `limit`
- `offset`

### History

- `GET /history`

By default, `/history` returns a compatibility array. When query parameters such as `limit`, `offset`, `analysis_name`, `date_from`, or `date_to` are used, it returns a paginated object.

### Operations

- `GET /health`
- `GET /metrics`
- `GET /diagnostics`
- `GET /analysis-jobs/stats`
- `GET /analysis-jobs/workers`
- `GET /analysis-jobs/failures?limit=10`

All standardized API errors include:

```json
{
  "error": "Human readable message",
  "error_code": "machine_readable_code",
  "status": 400
}
```

Requests and jobs support correlation IDs. Send `X-Correlation-ID` on `POST /analysis-jobs` to preserve the same trace value through the response, database job record, and worker logs.

---

## Useful Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `TVA_MAX_UPLOAD_BYTES` | `536870912` | Maximum upload size, 512 MB by default |
| `TVA_ALLOWED_VIDEO_EXTENSIONS` | `mp4,mov,avi,mkv,webm,m4v,mpeg,mpg` | Allowed upload extensions |
| `TVA_ALLOWED_CAMERA_SCHEMES` | `rtsp,rtsps,http,https` | Allowed stream URL schemes |
| `TVA_DATABASE_URI` | SQLite under `instance/` | Database connection |
| `TVA_UPLOAD_FOLDER` | `uploads` | Runtime upload directory |
| `TVA_OUTPUT_FOLDER` | `output` | Annotated video directory |
| `TVA_JOB_TIMEOUT_SECONDS` | `7200` | Worker timeout for long jobs |
| `TVA_WORKER_LEASE_SECONDS` | `30` | Duration of a worker's ownership lease |
| `TVA_WORKER_HEARTBEAT_SECONDS` | `10` | Lease refresh interval during model loading and processing |
| `TVA_MAINTENANCE_INTERVAL_SECONDS` | `300` | Worker maintenance interval |
| `TVA_JOB_RETENTION_HOURS` | `168` | Retention for terminal jobs and output files |
| `TVA_PIPELINE_RESIZE_DIM` | `1280,720` | Annotated output canvas size (inference runs on native frames) |
| `TVA_PIPELINE_IMGSZ` | `640` | YOLO inference resolution (aspect-preserving letterbox) |
| `TVA_PIPELINE_DETECTION_INTERVAL` | `2` | Run YOLO every Nth frame |
| `TVA_PIPELINE_TRACKER_BACKEND` | `bytetrack` | `bytetrack`, `botsort`, `centroid`, or `deepsort` |
| `TVA_PIPELINE_TRACKER_MIN_HITS` | `2` | Detections required before a track can be counted |
| `TVA_PIPELINE_CONFIDENCE_THRESHOLD` | `0.5` | Detection confidence cutoff (report-validated value) |
| `TVA_PIPELINE_NMS_IOU` | `0.7` | YOLO non-max-suppression IoU threshold |
| `TVA_PIPELINE_TRACK_CONF` | `0.5` | Detection floor fed to ByteTrack/BoT-SORT association (lower bridges occlusions, floods dense scenes) |
| `TVA_PIPELINE_CLASSIFICATION_THRESHOLD` | `0.4` | Minimum mean vote confidence before labeling |
| `TVA_PIPELINE_CLASSIFICATION_VOTE_SAMPLES` | `3` | Number of classifier samples to average per track |
| `TVA_PIPELINE_MIN_CROP` | `10` | Minimum crop size in 512px-equivalent pixels (auto-scaled to native) |
| `TVA_PIPELINE_ROI_POINTS` | unset | Counting ROI polygon as normalized `x,y;x,y;...` fractions |
| `TVA_PIPELINE_MODEL_PATH` | `yolo11n.pt` | YOLO weights file |
| `TVA_PIPELINE_CLASSIFIER_PATH` | `mobilenetv3_original.keras` | Classifier weights file |
| `TVA_PIPELINE_DEVICE` | auto | YOLO device override (e.g. `cuda:0`, `cpu`) |
| `TVA_PIPELINE_HALF` | `1` | FP16 inference when on CUDA |
| `TVA_SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite busy timeout for concurrent API/worker writes |
| `TVA_PROGRESS_SAVE_INTERVAL_SECONDS` | `2` | Minimum seconds between worker progress writes |
| `TVA_PROGRESS_SAVE_PERCENT_STEP` | `5` | Minimum progress change before forced DB write |
| `TVA_ANNOTATED_VIDEO_CODECS` | `avc1,H264,mp4v` | Ordered codec preference for annotated output |
| `TVA_DISABLE_GPT` | unset | Set truthy value to skip GPT calls |
| `TVA_ENABLE_TEST_ROUTES` | unset | Enable test-only routes in development |
| `TVA_YOLO_MODEL` | `yolo11n.pt` | Model filename shown by diagnostics |
| `TVA_CLASSIFIER_MODEL` | `mobilenetv3_original.keras` | Classifier filename shown by diagnostics |
| `TVA_DISK_WARN_BYTES` | `5368709120` | Warning threshold for free disk space |
| `TVA_DISK_CRITICAL_BYTES` | `1073741824` | Critical threshold for free disk space |

---

## Practical Smoke Check

After starting the backend, worker, and frontend, run a quick job through the frontend proxy:

```powershell
curl.exe -X POST "http://127.0.0.1:8080/analysis-jobs" `
  -F "video=@segments_segments_1.mp4;type=video/mp4" `
  -F "analysis_name=smoke_check" `
  -F "save_annotated=true" `
  -F "start_date=2024-07-07" `
  -F "start_time=09:00"
```

Then poll the returned job:

```powershell
Invoke-RestMethod "http://127.0.0.1:8080/analysis-jobs/<job_id>"
```

Expected result:

- status eventually becomes `completed`
- result contains vehicle counts and recommendations
- result contains `annotated_video` when annotated output was requested
- `http://127.0.0.1:8080/output/<annotated_video>` returns `Content-Type: video/mp4`

---

## Verification Commands

Backend:

```powershell
py -m unittest tests.test_pipeline_voting tests.test_app_routes tests.test_worker tests.test_trackers -v
py -m py_compile app.py worker.py backend\core.py backend\models.py backend\observability.py backend\routes.py backend\services.py backend\worker_runtime.py backend\inference\classification_voting.py backend\inference\pipeline.py backend\inference\trackers.py
```

Frontend:

```powershell
cd vehicle-webapp
npm.cmd run lint
npm.cmd run build
```

The production build may warn that `chunk-vendors` exceeds the default Vue CLI asset-size recommendation. That warning is expected with Vue and Chart.js in the current app.

---

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common setup and runtime issues, including queued jobs, annotated video playback, worker output, diagnostics, and generated files.

---

## Resetting Local State

To clear saved jobs and history:

1. Stop `python app.py`.
2. Stop `python worker.py`.
3. Delete `instance/analysis_history.db` and related SQLite journal/WAL files if present.
4. Restart the backend and worker.

Uploaded files and annotated outputs live separately in `uploads/` and `output/`.

---

## Research Notebooks

The repository includes notebooks used during experimentation and model development. They are not required to run the web app.

Examples:

- `Vehicle counting and classifcation.ipynb`
- dataset collection and preprocessing experiments
- early detection, tracking, and classification experiments

---

## Contact

For project questions or missing model assets, contact:

`jameskoh0513@gmail.com`
