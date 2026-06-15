# Vehicle Video Analyzer — FYP Submission Instructions

This tool analyzes traffic video or camera streams for billboard advertisers, providing vehicle counts, class breakdown, and actionable ad recommendations (using GPT or local logic). Analysis records are stored in a table for review.

---

## 1. Project Directories
Open command prompt and go to the project root (Traffic Video Analyzer)
```
cd <path/to/Traffic Video Analyzer>
```

Backend code is now organized under the `backend/` folder, while `app.py`, `worker.py`, `analysis.py`, and `pipeline.py` remain thin compatibility entrypoints.
The heavy inference code lives in `backend/inference/`.

## 2. Backend Setup

1. (Recommended/optional) Create a virtual environment:
   ```
   python -m venv venv
   # Activate (Windows): venv\Scripts\activate
   # Activate (Linux/Mac): source venv/bin/activate
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up environment variable for OpenAI (if using GPT):
   - add your OpenAI API key into .env file.
   - If not available, leave blank (local analysis will be used).

---

## 3. Frontend Setup

1. In the vehicle-webapp folder:
   ```
   cd vehicle-webapp
   npm install
   ```
2. Run the frontend:
   ```
   npm run serve
   ```
   - Opens at [http://localhost:8080](http://localhost:8080) by default.

---

## 4. Run the Backend

Open another command prompt, go to the Traffic Video Analyzer directory again, enter:

```
python app.py
```

- Backend API at [http://localhost:5000](http://localhost:5000)

## 4b. Run the Analysis Worker

Open one more command prompt, go to the Traffic Video Analyzer directory again, enter:

```
python worker.py
```

- This worker picks up queued analysis jobs from the database and processes them in the background.
- If the worker is not running, uploaded jobs will remain in `queued` status.
- The worker also runs periodic maintenance, including automatic pruning of old finished jobs and annotated output files.

---

## 4c. Backend Ops Endpoints

These endpoints help you monitor and operate the async analysis queue:

- `GET /health` returns app health, database status, and a queue snapshot.
- `GET /analysis-jobs?status=queued&limit=20` lists recent jobs with optional status filtering.
- `GET /analysis-jobs/stats` returns queue depth, status counts, stale leases, and active worker count.
- `GET /analysis-jobs/workers` lists active workers, their current jobs, heartbeat times, and lease expiry times.
- `GET /analysis-jobs/failures?limit=10` lists recent failed jobs with normalized failure reasons.
- `GET /metrics` returns Prometheus-style metrics for queue depth, worker activity, job durations, failure reasons, history totals, and database availability.
- `GET /diagnostics` returns runtime configuration, model-file checks, upload/output path checks, and available disk space.
- `POST /analysis-jobs/<job_id>/retry` re-queues a failed or canceled job for another attempt.
- `POST /analysis-jobs/<job_id>/cancel` requests cancellation for a queued or running job.
- `POST /analysis-jobs/prune` removes old completed/failed/canceled jobs and annotated video files based on retention.
- Backend and worker lifecycle events are emitted as structured JSON log lines to standard logging output.
- Requests and jobs carry a correlation ID. You can send `X-Correlation-ID` on `POST /analysis-jobs`, and the backend will preserve it on the job record, response header, and worker logs.
- Error responses now include both `error` and a machine-friendly `error_code`.

---

## 4d. Useful Backend Environment Variables

- `TVA_MAX_UPLOAD_BYTES`: maximum upload size in bytes. Default is `536870912` (512 MB).
- `TVA_ALLOWED_VIDEO_EXTENSIONS`: comma-separated allowed upload extensions. Default is `mp4,mov,avi,mkv,webm,m4v,mpeg,mpg`.
- `TVA_ALLOWED_CAMERA_SCHEMES`: allowed camera URL schemes. Default is `rtsp,rtsps,http,https`.
- `TVA_JOB_TIMEOUT_SECONDS`: maximum worker processing time before a job is treated as timed out. Default is `7200`.
- `TVA_MAINTENANCE_INTERVAL_SECONDS`: how often the worker runs automatic pruning. Default is `300`.
- `TVA_JOB_RETENTION_HOURS`: how long completed/failed/canceled jobs and annotated outputs are kept before pruning. Default is `168`.
- `TVA_PIPELINE_RESIZE_DIM`: processing resolution as `width,height` or `widthxheight`. Default is `512,384`.
- `TVA_PIPELINE_DETECTION_INTERVAL`: run YOLO every Nth frame instead of every frame. Default is `2`.
- `TVA_PIPELINE_PROGRESS_REPORT_FRAMES`: how many processed frames between pipeline progress reports. Default is `45`.
- `TVA_PIPELINE_TRACKER_BACKEND`: tracker backend for the pipeline. Default is `centroid`. The heavier alternative is `deepsort`.
- `TVA_YOLO_MODEL`: model filename/path shown by diagnostics for YOLO readiness checks. Default is `yolo11n.pt`.
- `TVA_CLASSIFIER_MODEL`: model filename/path shown by diagnostics for classifier readiness checks. Default is `mobilenetv3_original.keras`.
- `TVA_DISK_WARN_BYTES`: free-space threshold where diagnostics marks a path as `warning`. Default is 5 GB.
- `TVA_DISK_CRITICAL_BYTES`: free-space threshold where diagnostics marks a path as `critical`. Default is 1 GB.
- `TVA_PROGRESS_SAVE_INTERVAL_SECONDS`: minimum seconds between worker progress writes to the database. Default is `2`.
- `TVA_PROGRESS_SAVE_PERCENT_STEP`: minimum progress-percent jump before forcing a worker progress write. Default is `5`.
- `TVA_ENABLE_TEST_ROUTES`: set to `true` only in development if you need the debug/test routes.

---

## 5. Usage Steps

1. Open [http://localhost:8080](http://localhost:8080) in your browser.
2. Upload a video or enter a camera/IP stream URL.
3. (Optional) Enter video start date/time and analysis record name.
4. Click "Analyze Video" and wait for results.
5. View: vehicle counts, charts, annotated video, insights & recommendations, and analysis history.

---

## 6. Resetting the Database

To clear all previous analysis records:

- Stop the backend (Ctrl+C in terminal)
- Delete `analysis_history.db` (and any related journal/WAL files)
- Restart the backend (`python app.py`).

---

## 7. Important Notes

- Model files **must** be present or video analysis will fail.
- OpenAI GPT is optional; local recommendations are always available.
- Uploads are now validated by extension and size before entering the analysis queue.
- Camera stream sources must be an integer device index or a direct `rtsp`, `rtsps`, `http`, or `https` stream URL.
- YouTube page URLs such as `youtube.com/watch?...` or `youtu.be/...` are not supported input sources.
- The default pipeline is now tuned more for speed: lower processing resolution, detection every 2 frames, reduced worker progress-write frequency, and the lighter `centroid` tracker by default.
- You can compare tracker backends with `py benchmark_trackers.py --video <path-to-video>` or run a quick synthetic-only comparison with `py benchmark_trackers.py`.
- `GET /analysis-jobs` now supports `status`, `source_kind`, `analysis_name`, `limit`, and `offset`.
- `GET /history` still returns a simple array by default for compatibility, but returns a paginated object when query parameters such as `analysis_name`, `limit`, or `offset` are used.
- All required dependencies are listed in requirements.txt and package.json.

---

## 8. Contact

For any issues or if model files are missing, contact the project author. 
email : jameskoh0513@gmail.com

---

**Thank you for reviewing this Final Year Project!**

