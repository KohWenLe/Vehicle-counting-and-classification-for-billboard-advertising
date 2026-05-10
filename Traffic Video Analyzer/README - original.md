# Vehicle Video Analyzer for Billboard Advertising

A traffic video analytics system for billboard advertising decisions.

The project accepts uploaded traffic footage or supported camera stream inputs, detects and classifies vehicles, summarizes traffic behavior, and produces advertising-oriented recommendations. It includes a Vue frontend, a Flask API, an async worker process, historical analysis storage, and benchmarking utilities for tracker performance.

---

## Project Overview

Outdoor advertisers often need more than raw traffic volume. They need to understand:

- what types of vehicles dominate a location
- when traffic peaks happen
- whether the audience mix supports premium, commuter, or commercial targeting

This project provides:

- vehicle counting by class
- time-series traffic analysis
- peak-hour detection
- billboard-focused recommendations
- optional GPT-based recommendation generation
- saved analysis history with queue/job tracking

---

## Current Features

### Detection, Tracking, and Classification

- YOLO for vehicle detection
- tracker-selectable pipeline
  - default: lightweight `centroid` tracker for better speed
  - optional: `deepsort`
- custom MobileNetV3 classifier for vehicle class labeling

### Vehicle Classes

- High-End Vehicles
- Mid-Range Vehicles
- Low-End Vehicles
- Commercial Vehicles
- Motorcycle
- Unclassified

### Analytics

- cumulative counts
- sampled time-series summaries
- peak-hour estimation
- local rule-based recommendations
- optional GPT recommendations when an OpenAI API key is configured

### Web Application

- upload a video file
- submit a supported camera stream source
- async analysis jobs with queue status and progress updates
- recent jobs panel with retry/cancel controls
- paginated and filterable history
- results charts and recommendation panels
- optional annotated output video

### Backend Operations

- persistent job queue in SQLite
- separate analysis worker process
- cancellation and retry endpoints
- queue stats, health, and metrics endpoints
- structured JSON logging
- retention-based pruning of finished jobs and output files

---

## Current System Architecture

```text
Frontend (Vue.js)
    ->
Flask API
    ->
SQLite-backed Analysis Job Queue
    ->
Worker Process
    ->
Video Pipeline (YOLO + Tracker + MobileNetV3)
    ->
Analytics Engine (Local rules, optional GPT)
    ->
SQLite History + Optional Annotated Output
```

### Backend Layout

Backend code is organized under `backend/`:

- `backend/core.py`: app config, environment, shared defaults
- `backend/models.py`: SQLAlchemy models and database setup
- `backend/routes.py`: API routes and request validation
- `backend/services.py`: analysis orchestration and persistence helpers
- `backend/worker_runtime.py`: worker loop, leasing, progress, recovery
- `backend/inference/pipeline.py`: frame processing pipeline
- `backend/inference/analysis.py`: local traffic insight logic
- `backend/inference/trackers.py`: tracker backends

Compatibility entrypoints remain at the project root:

- `app.py`
- `worker.py`
- `analysis.py`
- `pipeline.py`

---

## Input Support

### Supported Inputs

- uploaded video files with allowed extensions such as `mp4`, `mov`, `avi`, `mkv`, `webm`, `m4v`, `mpeg`, `mpg`
- numeric device index such as `0`
- direct `rtsp`, `rtsps`, `http`, or `https` camera stream URLs

### Unsupported Inputs

- YouTube page URLs such as `youtube.com/watch?...`
- short YouTube share URLs such as `youtu.be/...`
- non-stream URLs that OpenCV cannot consume as a direct video source

The frontend and backend both validate these restrictions.

---

## Performance Notes

The current default pipeline is tuned more for speed than the earliest version of the repo:

- lower default processing resolution
- detection every 2 frames instead of every frame
- reduced worker progress-write frequency
- lighter `centroid` tracker as the default backend
- frame drawing skipped unless display or annotated output is needed

You can also benchmark tracker backends directly:

```bash
py benchmark_trackers.py
py benchmark_trackers.py --video <path-to-video>
```

---

## Requirements

- Python 3.8+
- Node.js 16+
- npm

---

## Setup

Open a terminal and go to the project root:

```bash
cd <path/to/Traffic Video Analyzer>
```

Optional but recommended:

```bash
python -m venv venv
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### Backend Dependencies

```bash
pip install -r requirements.txt
```

### Optional GPT Configuration

Create a `.env` file and add:

```env
OPENAI_API_KEY=your_api_key_here
```

If no API key is available, the system falls back to local recommendation logic.

### Frontend Dependencies

```bash
cd vehicle-webapp
npm install
```

---

## Running the System

### 1. Start the Backend API

From the project root:

```bash
python app.py
```

API default:

```text
http://localhost:5000
```

### 2. Start the Analysis Worker

In another terminal, from the project root:

```bash
python worker.py
```

The worker:

- claims queued jobs
- processes video analysis in the background
- updates job progress
- supports cancellation and recovery
- runs periodic maintenance and pruning

If the worker is not running, jobs will stay queued.

### 3. Start the Frontend

In another terminal:

```bash
cd vehicle-webapp
npm run serve
```

Frontend default:

```text
http://localhost:8080
```

---

## How to Use

1. Open `http://localhost:8080`
2. Choose either:
   - upload a video file
   - enter a supported direct camera stream URL or numeric device index
3. Optionally set:
   - start date
   - start time
   - analysis name
   - save annotated output
4. Submit the analysis
5. Monitor:
   - queue/running state
   - progress updates
   - recent jobs
6. Review:
   - class counts
   - charts
   - peak-hour summary
   - recommendations
   - history records

---

## Backend Ops Endpoints

- `GET /health`
- `GET /metrics`
- `GET /analysis-jobs`
- `GET /analysis-jobs/<job_id>`
- `GET /analysis-jobs/stats`
- `POST /analysis-jobs`
- `POST /analysis-jobs/<job_id>/cancel`
- `POST /analysis-jobs/<job_id>/retry`
- `POST /analysis-jobs/prune`
- `GET /history`

Notes:

- error responses include both `error` and `error_code`
- `/history` supports paginated/filterable responses when query parameters are used
- `/analysis-jobs` supports filtering by status, source kind, and analysis name

---

## Useful Environment Variables

- `TVA_MAX_UPLOAD_BYTES`
- `TVA_ALLOWED_VIDEO_EXTENSIONS`
- `TVA_ALLOWED_CAMERA_SCHEMES`
- `TVA_JOB_TIMEOUT_SECONDS`
- `TVA_MAINTENANCE_INTERVAL_SECONDS`
- `TVA_JOB_RETENTION_HOURS`
- `TVA_PIPELINE_RESIZE_DIM`
- `TVA_PIPELINE_DETECTION_INTERVAL`
- `TVA_PIPELINE_PROGRESS_REPORT_FRAMES`
- `TVA_PIPELINE_TRACKER_BACKEND`
- `TVA_PIPELINE_CLASSIFICATION_VOTE_SAMPLES`
- `TVA_PROGRESS_SAVE_INTERVAL_SECONDS`
- `TVA_PROGRESS_SAVE_PERCENT_STEP`
- `TVA_ENABLE_TEST_ROUTES`

Current default tracker backend:

```text
centroid
```

Optional heavier tracker:

```text
deepsort
```

---

## Resetting the Database

To clear saved analysis history:

1. Stop the backend and worker.
2. Delete `instance/analysis_history.db` and any related journal or WAL files if present.
3. Restart the backend and worker.

---

## Research and Model Development Notebooks

This repository also includes notebooks used during research and model development. They are not required to run the final app, but are kept for transparency and academic review.

Examples include:

- `Vehicle counting and classifcation.ipynb`
- dataset collection and preprocessing experiments
- early detection/tracking/classification experiments

Important:

- these notebooks are not executed by the Flask app
- running the system does not require Jupyter

---

## Notes and Known Reality

- model files must be present or analysis will fail
- GPT is optional, not required
- tracker benchmarking utilities are included, but benchmark speed is not the same thing as full counting accuracy
- the current system is much more robust than the original single-request pipeline, but still benefits from further tuning on real traffic footage

---

## Contact

For questions, missing model assets, or clarification, contact the project author:

`jameskoh0513@gmail.com`

---
