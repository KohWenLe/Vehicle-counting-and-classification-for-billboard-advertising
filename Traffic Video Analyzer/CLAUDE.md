# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A web app that turns roadside traffic footage into billboard-advertising planning data. Users upload a video or point at a camera stream; the system detects, tracks, and classifies vehicles, then returns a traffic-mix summary and ad recommendations. There are **three runtime processes**: Vue frontend, Flask API, and a separate Python worker.

## Commands

All commands run from the project root (Windows / PowerShell) unless noted.

```powershell
# Backend setup
python -m venv venv; venv\Scripts\activate; pip install -r requirements.txt

# Run the three processes (separate terminals)
python app.py        # Flask API on :5000
python worker.py     # job-processing worker (idle when queue is empty — normal)
cd vehicle-webapp; npm run serve   # frontend on :8080, proxies API routes to :5000

# Worker single-shot (process one job and exit — useful for debugging)
python worker.py --once
```

Tests and verification:

```powershell
# Full backend suite
py -m unittest tests.test_pipeline_voting tests.test_counting tests.test_app_routes tests.test_worker tests.test_trackers -v

# Single test module / case / method
py -m unittest tests.test_worker -v
py -m unittest tests.test_worker.SomeTestCase.test_method

# Syntax compile check across backend
py -m py_compile app.py worker.py backend\core.py backend\models.py backend\observability.py backend\routes.py backend\services.py backend\worker_runtime.py backend\inference\classification_voting.py backend\inference\counting.py backend\inference\pipeline.py backend\inference\trackers.py

# Frontend
cd vehicle-webapp; npm.cmd run lint; npm.cmd run build

# Counting-accuracy regression harness (ground truth parsed from "<N>vehicles" in filename)
# Reference clips: cam1_46vehicles_passed.mp4, cam2_53vehicles_passed.mp4 (repo root, git-ignored)
venv\Scripts\python.exe evaluate_counting.py --label my-config --tracker centroid --conf 0.5
```

`tests/test_analysis.py` exists but is not in the standard suite list above. Note the imports use `py` / `npm.cmd` — the worker and pipeline tests stub out heavy ML deps, so the suite runs without GPU or model files.

## Architecture

### Two processes, one shared Flask app

`app.py` (API) and `worker.py` (worker loop) are **separate OS processes that share the same SQLite database and the same `backend.core.app`/`db` objects**. They do not talk over HTTP — they coordinate entirely through the `analysis_job` table. The API enqueues jobs; the worker polls, claims, and processes them.

### Job lifecycle (the core of the system)

Jobs flow `queued → running → completed | failed | canceled` and live in `AnalysisJob` ([backend/models.py](backend/models.py)). The worker ([backend/worker_runtime.py](backend/worker_runtime.py)) implements a **lease + heartbeat protocol** so a crashed worker doesn't strand a job:

- `claim_next_job` atomically flips a row to `running` via a conditional `UPDATE ... WHERE` and checks the affected row count to avoid two workers grabbing the same job.
- While processing, a background heartbeat thread (`_lease_heartbeat_loop`) refreshes `lease_expires_at`. If the lease expires, another worker (or `recover_abandoned_jobs` at startup) reclaims or re-queues the job.
- **Cancellation** is cooperative: the API sets `cancel_requested`; the pipeline polls `should_cancel` and raises `AnalysisCancelled`. Same channel handles timeout (`TVA_JOB_TIMEOUT_SECONDS`) and worker-lost detection (`_job_stop_reason`).
- Progress writes are throttled (`_refresh_job_lease`) by both time delta and percent delta to limit DB churn.

When editing worker logic, preserve the "does this worker still own the job?" guards (`_worker_owns_job`) before committing results — they prevent a reclaimed job's stale worker from overwriting fresh state.

### The facade / module-reload pattern

`app.py`, `worker.py`, `analysis.py`, and `pipeline.py` at the root are **thin compatibility facades** over the real code in `backend/`. The entrypoints (`app.py`, `worker.py`) deliberately purge and re-import all `backend.*` modules via `importlib` before re-exporting symbols, so each process starts from clean module state. `worker.py` additionally re-binds `execute_analysis`/`prune_terminal_jobs` onto the runtime module (`_sync_runtime_dependencies`) so test monkeypatches take effect. **Add new behavior in `backend/`, not in the root facades.** Tests and the legacy code import from these root names (e.g. `from pipeline import process_video`), so keep the re-exports intact.

### Import-time side effects

Importing `backend.core` **creates the Flask app, the SQLAlchemy `db`, and the `instance/`, `uploads/`, `output/` folders**, and reads all config from env vars into module-level constants. Importing `backend.models` runs `initialize_database()` (creates tables + applies manual schema migrations). Because config is captured at import time, env vars must be set before import.

### Manual SQLite migrations

There is no Alembic. `backend/models.py` (`_ensure_analysis_job_columns`, `_ensure_analysis_job_indexes`) hand-applies `ALTER TABLE ... ADD COLUMN` and `CREATE INDEX IF NOT EXISTS` against the live DB via `PRAGMA table_info`. When you add a column to `AnalysisJob`, also add its migration entry here, or existing databases will break.

### Inference pipeline

[backend/inference/pipeline.py](backend/inference/pipeline.py) `process_video` is the heavy loop: YOLO (`yolo11n.pt`) detection every Nth frame → tracker (`centroid` default, or `deepsort`) → **entry-based ROI counting**: a vehicle is counted the moment its tracked centroid enters the region-of-interest polygon (held under `Unclassified`), then MobileNetV3 **multi-frame voting** ([classification_voting.py](backend/inference/classification_voting.py)) resolves the label afterward and the count is *moved* to the voted class. Counting never depends on classification readiness — this matches the original methodology report (`traffic-video-analytics-part-of-original-report.pdf`, §3.5), which is the authoritative design + evaluation reference. Tracks must survive `min_hits` detections before they can be counted. Models are cached process-wide in `_MODEL_CACHE` under a lock. Counts and `time_series` are **cumulative totals**, not per-interval flows — the GPT prompt and analytics depend on this (per-class values may dip when a pending label resolves; the total never does).

Recommendations come from [backend/inference/analysis.py](backend/inference/analysis.py) (local logic, always available) and optionally GPT ([services.py](backend/services.py) `analyze_with_gpt`, gated by `OPENAI_API_KEY` / `TVA_DISABLE_GPT`). GPT failures are swallowed and fall back to local logic.

### Frontend

Vue 3 + Chart.js in [vehicle-webapp/](vehicle-webapp/). It is async-polling: submit a job, then poll `GET /analysis-jobs/<id>` until terminal. The dev server proxies `/analysis-jobs`, `/output`, `/history`, `/health`, `/metrics`, `/diagnostics`, etc. to `:5000` ([vue.config.js](vehicle-webapp/vue.config.js)) — so the frontend talks to its own origin and the proxy reaches Flask.

## Conventions worth knowing

- **Pipeline tuning is via `TVA_*` env vars**, surfaced as `DEFAULT_PIPELINE_*` constants in [backend/core.py](backend/core.py) and threaded through `services.run_video_pipeline`. Don't hardcode pipeline params in the pipeline call site — add an env-backed default in core.
- **API errors** use a standard shape (`error`, `error_code`, `status`) via `ApiError`/`_error_response` in [backend/routes.py](backend/routes.py). Reuse it for new endpoints.
- **Correlation IDs**: `X-Correlation-ID` is attached per request (`attach_correlation_id`) and persisted on the job so a trace spans request → DB → worker logs. Structured logs go through `log_event` in [backend/observability.py](backend/observability.py).
- YouTube page URLs are intentionally rejected as camera sources (OpenCV can't read them); see `UNSUPPORTED_CAMERA_URL_HOSTS`.
- Generated dirs (`output/`, `uploads/`, `runtime_logs/`, `instance/`, `__pycache__/`, `venv/`) are runtime artifacts, not source.

See [README.md](README.md) for the full env-var table, API endpoint list, and smoke-check curl recipe; [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for runtime issues.
