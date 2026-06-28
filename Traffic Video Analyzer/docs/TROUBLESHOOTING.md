# Troubleshooting Guide

This guide covers the most common local setup and runtime issues for Traffic Video Analyzer.

---

## Required Processes

For normal use, run all three processes:

```powershell
python app.py
python worker.py
cd vehicle-webapp
npm run serve
```

The frontend can submit jobs without the worker, but those jobs will stay in `queued` status until `python worker.py` is running.

---

## Worker Looks Idle

This is normal when there are no queued jobs. The worker polls the database quietly.

Check whether the API sees queued jobs:

```powershell
Invoke-RestMethod "http://127.0.0.1:5000/analysis-jobs/stats"
```

Useful signs:

- `queue_depth > 0`: jobs are waiting
- `active_workers > 0`: a worker currently owns a running job
- `stale_leases > 0`: a worker may have stopped while processing

---

## Job Fails With "Cannot Open Video Source"

If the upload existed when the job was submitted but disappears before OpenCV opens it, check for old worker processes still running from previous terminals or background sessions.

The worker now refreshes its lease independently during slow TensorFlow/model loading, and a worker that loses job ownership will not delete the upload. Restart all backend and worker processes after updating so every running process uses the fixed code.

Relevant settings:

```text
TVA_WORKER_LEASE_SECONDS=30
TVA_WORKER_HEARTBEAT_SECONDS=10
```

The heartbeat interval must remain shorter than the lease duration.

---

## Frontend Shows API 404 Errors

If the browser console shows a request such as `/analysis-jobs`, `/metrics`, `/health`, `/diagnostics`, or `/output/...` returning `404` from port `8080`, the Vue dev server proxy may not be running with the latest `vue.config.js`.

Fix:

1. Stop `npm run serve`.
2. Start it again:

```powershell
cd vehicle-webapp
npm run serve
```

The frontend dev server proxies backend routes to `http://localhost:5000`.

---

## Jobs Stay Queued

Likely causes:

- `python worker.py` is not running
- the worker is using a different database path or environment
- an old worker lease is stale

Checks:

```powershell
Invoke-RestMethod "http://127.0.0.1:5000/health"
Invoke-RestMethod "http://127.0.0.1:5000/analysis-jobs/stats"
Invoke-RestMethod "http://127.0.0.1:5000/analysis-jobs/workers"
```

If the app and worker use custom environment variables such as `TVA_DATABASE_URI`, make sure both terminals use the same values.

---

## Annotated Video Is Missing Or Does Not Play

First confirm the job result contains `annotated_video`.

```powershell
Invoke-RestMethod "http://127.0.0.1:5000/analysis-jobs/<job_id>"
```

Then confirm the generated file exists:

```powershell
Get-ChildItem output
```

Then check the output route:

```powershell
Invoke-WebRequest "http://127.0.0.1:5000/output/<filename>.mp4" -Method Head
Invoke-WebRequest "http://127.0.0.1:8080/output/<filename>.mp4" -Method Head
```

Expected:

- status code `200`
- `Content-Type` is `video/mp4`
- `Content-Length` is greater than `0`

If the video exists but the browser cannot play it, OpenCV may have used a codec your browser does not support. The pipeline tries codecs in this order by default:

```text
avc1,H264,mp4v
```

You can override the order:

```powershell
$env:TVA_ANNOTATED_VIDEO_CODECS="mp4v"
python worker.py
```

Restart the worker after changing codec environment variables.

---

## Same Video Produces Slightly Different Class Counts

This can happen because object detection, tracking, and classification are frame-dependent. The current pipeline reduces this by averaging multiple classifier samples per track.

Default:

```text
TVA_PIPELINE_CLASSIFICATION_VOTE_SAMPLES=3
```

To test stability:

```powershell
py validate_pipeline_voting.py --video segments_segments_1.mp4 --runs 2 --vote-samples 3
```

Tradeoff:

- higher vote samples can improve stability
- higher vote samples can delay classification until more frames are available
- very short or partially visible tracks may still become `Unclassified`

---

## Upload Or Camera URL Is Rejected

Supported uploaded video extensions are configured by:

```text
TVA_ALLOWED_VIDEO_EXTENSIONS
```

Default:

```text
mp4,mov,avi,mkv,webm,m4v,mpeg,mpg
```

Supported camera URL schemes are configured by:

```text
TVA_ALLOWED_CAMERA_SCHEMES
```

Default:

```text
rtsp,rtsps,http,https
```

YouTube page URLs are intentionally blocked because they are not direct camera/video streams.

---

## Diagnostics Reports Degraded

Check:

```powershell
Invoke-RestMethod "http://127.0.0.1:5000/diagnostics"
```

Common degraded causes:

- `yolo11n.pt` is missing
- `mobilenetv3_original.keras` is missing
- `uploads/` or `output/` is missing or not writable
- free disk space is below the configured warning or critical threshold

Relevant variables:

```text
TVA_YOLO_MODEL
TVA_CLASSIFIER_MODEL
TVA_UPLOAD_FOLDER
TVA_OUTPUT_FOLDER
TVA_DISK_WARN_BYTES
TVA_DISK_CRITICAL_BYTES
```

---

## Runtime Files Dirty The Git Working Tree

The app creates runtime files in:

- `output/`
- `uploads/`
- `runtime_logs/`
- `instance/`
- `tests_artifacts/`
- `__pycache__/`

These are generated artifacts. They should usually not be committed.

If `output/segment_try1.mp4` appears as deleted after running the worker, that means the worker retention cleanup pruned an old tracked output file. Decide explicitly whether to keep that file in Git or remove it from the repository history going forward.

---

## Useful Smoke Check

Submit the bundled short sample through the frontend proxy:

```powershell
curl.exe -X POST "http://127.0.0.1:8080/analysis-jobs" `
  -F "video=@segments_segments_1.mp4;type=video/mp4" `
  -F "analysis_name=smoke_check" `
  -F "save_annotated=true" `
  -F "start_date=2024-07-07" `
  -F "start_time=09:00"
```

Poll the returned job:

```powershell
Invoke-RestMethod "http://127.0.0.1:8080/analysis-jobs/<job_id>"
```

A successful run reaches `completed`, returns counts, and creates an annotated MP4 in `output/`.

---

## Verification Commands

Backend:

```powershell
py -m unittest tests.test_pipeline_voting tests.test_app_routes tests.test_worker tests.test_trackers -v
```

Frontend:

```powershell
cd vehicle-webapp
npm.cmd run lint
npm.cmd run build
```
