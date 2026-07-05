import datetime
import os
import re
import threading
import time

import cv2
import numpy as np
import tensorflow as tf
from tensorflow.keras.applications.mobilenet_v3 import preprocess_input as keras_preprocess
from tensorflow.keras.preprocessing.image import img_to_array
from ultralytics import YOLO
from backend.inference.classification_voting import TrackClassificationVotes
from backend.inference.counting import RoiEntryCounter
from backend.inference.overlay import draw_counting_zone, draw_hud, draw_track, draw_watermark
from backend.inference.trackers import TrackerTrack, build_tracker_backend


ULTRALYTICS_TRACKERS = {"bytetrack", "botsort"}


_MODEL_CACHE = {}
_MODEL_LOCK = threading.Lock()


class AnalysisCancelled(RuntimeError):
    pass


def load_classifier_with_architecture(classifier_path):
    from tensorflow.keras.applications import MobileNetV3Small
    from tensorflow.keras.layers import Dense, Dropout, GlobalAveragePooling2D
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.regularizers import l2

    base_model = MobileNetV3Small(
        input_shape=(224, 224, 3),
        include_top=False,
        weights=None,
    )

    model = Sequential(
        [
            base_model,
            GlobalAveragePooling2D(),
            Dense(256, activation="relu", kernel_regularizer=l2(0.001)),
            Dropout(0.4),
            Dense(5, activation="softmax"),
        ]
    )
    model.load_weights(classifier_path)
    return model


def _get_cached_models(model_path, classifier_path, track_variant=False):
    # model.track() permanently registers tracking callbacks on a YOLO
    # instance, which would contaminate plain detection calls made later by
    # other jobs in this process — so tracking mode gets its own cached model.
    yolo_key = "yolo_track" if track_variant else "yolo"
    with _MODEL_LOCK:
        if _MODEL_CACHE.get(f"{yolo_key}_path") != model_path:
            _MODEL_CACHE[yolo_key] = YOLO(model_path)
            _MODEL_CACHE[f"{yolo_key}_path"] = model_path

        if _MODEL_CACHE.get("classifier_path") != classifier_path:
            try:
                classifier_model = load_classifier_with_architecture(classifier_path)
            except Exception as exc:
                print(f"Failed to load classifier via weights-only path: {exc}")
                classifier_model = tf.keras.models.load_model(
                    classifier_path,
                    compile=False,
                    safe_mode=False,
                )

            _MODEL_CACHE["classifier"] = classifier_model
            _MODEL_CACHE["classifier_path"] = classifier_path

        return _MODEL_CACHE[yolo_key], _MODEL_CACHE["classifier"]


def _has_gpu():
    try:
        return bool(tf.config.list_physical_devices("GPU"))
    except Exception:
        return False


def _resolve_yolo_device():
    """YOLO runs on PyTorch, so probe torch (not TensorFlow) for CUDA."""
    configured = os.getenv("TVA_PIPELINE_DEVICE", "").strip()
    if configured:
        return configured
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
    except Exception:
        pass
    return "cpu"


def _is_cuda_device(device):
    # Ultralytics accepts both "cuda:0" and bare GPU indices like "0" or "0,1".
    normalized = str(device).strip().lower()
    return normalized.startswith("cuda") or normalized.split(",")[0].strip().isdigit()


def _build_roi_polygon(roi_points, width, height):
    if roi_points is None:
        y0, y1 = int(height / 4), int(height * 3 / 4)
        x0, x1 = int(width / 4), int(width * 3 / 4)
        roi_points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    elif all(0 <= x <= 1 and 0 <= y <= 1 for x, y in roi_points):
        # Coordinates that all fall in [0, 1] are normalized fractions of the
        # frame, so the same ROI config works at any input resolution.
        roi_points = [(int(x * width), int(y * height)) for x, y in roi_points]
    return np.array(roi_points, dtype=np.int32)


_TRACKER_CLASS_NAMES = {"bytetrack": "BYTETracker", "botsort": "BOTSORT"}


def _reset_ultralytics_tracker(yolo_model, tracker_type):
    """Start each video with fresh tracker state on the cached model.

    Same backend: reset() the existing instances in place. Deleting them
    instead would make model.track re-register its callbacks (it registers
    whenever predictor.trackers is missing), and duplicated callbacks update
    the tracker twice per frame, destroying association.

    Different backend requested: the persisted instances pin the tracker TYPE
    (the yaml is only read at creation), so drop them AND strip the old
    tracking callbacks so the re-registration cannot duplicate.
    """
    predictor = getattr(yolo_model, "predictor", None)
    trackers = getattr(predictor, "trackers", None)
    if not trackers:
        return
    expected_class = _TRACKER_CLASS_NAMES.get(tracker_type)
    if all(type(tracker).__name__ == expected_class for tracker in trackers):
        for tracker in trackers:
            tracker.reset()
        return
    del predictor.trackers
    for event in ("on_predict_start", "on_predict_postprocess_end"):
        yolo_model.callbacks[event] = [
            callback
            for callback in yolo_model.callbacks[event]
            if getattr(getattr(callback, "func", callback), "__module__", "") != "ultralytics.trackers.track"
        ]


def _safe_output_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip()).strip("._")
    return cleaned or f"analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _is_stream_source(video_path):
    if isinstance(video_path, int):
        return True
    if not isinstance(video_path, str):
        return False
    lowered = video_path.lower()
    return lowered.startswith("rtsp://") or lowered.startswith("rtsps://") or lowered.startswith("http://") or lowered.startswith("https://")


def _open_video_writer(output_path, fps, frame_size):
    preferred_codecs = ["avc1", "H264", "mp4v"]
    raw_value = os.getenv("TVA_ANNOTATED_VIDEO_CODECS", "")
    if raw_value.strip():
        preferred_codecs = [codec.strip() for codec in raw_value.split(",") if codec.strip()]

    for codec in preferred_codecs:
        fourcc = cv2.VideoWriter_fourcc(*codec)
        writer = cv2.VideoWriter(output_path, fourcc, fps, frame_size)
        if writer.isOpened():
            return writer, codec
        writer.release()

    return None, None


def process_video(
    video_path,
    start_dt=None,
    resize_dim=(1280, 720),
    denoise=False,
    roi_points=None,
    model_path="yolo11n.pt",
    classifier_path="mobilenetv3_original.keras",
    detection_interval=2,
    detection_imgsz=640,
    confidence_threshold=0.5,
    tracker_feed_conf=0.5,
    nms_iou=0.7,
    min_w=10,
    min_h=10,
    classification_threshold=0.4,
    custom_classes=None,
    save_annotated=False,
    analysis_name=None,
    output_dir="output",
    display=False,
    time_series_interval_seconds=5,
    progress_report_frames=45,
    tracker_backend="bytetrack",
    tracker_min_hits=2,
    classification_vote_samples=3,
    progress_callback=None,
    should_cancel=None,
):
    yolo_class_names = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
    if custom_classes is None:
        custom_classes = [
            "Commercial Vehicles",
            "High-End Vehicles",
            "Low-End Vehicles",
            "Mid-Range Vehicles",
            "Motorcycle",
        ]

    normalized_backend = (tracker_backend or "centroid").strip().lower()
    use_ultralytics_tracking = normalized_backend in ULTRALYTICS_TRACKERS
    yolo_model, classifier_model = _get_cached_models(
        model_path, classifier_path, track_variant=use_ultralytics_tracking
    )

    if start_dt is None:
        start_dt = datetime.datetime.now()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    # Detection, tracking, ROI, and classifier crops all work in NATIVE frame
    # coordinates so no pixel information is destroyed before inference.
    # resize_dim only sets the annotated-output canvas size.
    out_width, out_height = resize_dim
    detection_interval = max(1, int(detection_interval or 1))
    detection_imgsz = max(64, int(detection_imgsz or 640))
    progress_report_frames = max(1, int(progress_report_frames or 1))
    classification_vote_samples = max(1, int(classification_vote_samples or 1))
    should_draw_annotations = bool(display or save_annotated)

    native_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    native_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    roi_polygon = None
    # min_w/min_h were tuned on 512px-wide frames; scale them with the native
    # width so far-away sub-vehicle blobs stay rejected at higher resolutions.
    effective_min_w, effective_min_h = min_w, min_h
    if native_width > 0 and native_height > 0:
        roi_polygon = _build_roi_polygon(roi_points, native_width, native_height)
        crop_scale = max(1.0, native_width / 512.0)
        effective_min_w = max(1, int(min_w * crop_scale))
        effective_min_h = max(1, int(min_h * crop_scale))

    annotated_video = None
    if save_annotated:
        os.makedirs(output_dir, exist_ok=True)
        annotated_video = f"{_safe_output_name(analysis_name)}.mp4"
        output_path = os.path.join(output_dir, annotated_video)
        out_writer, selected_codec = _open_video_writer(output_path, fps, (out_width, out_height))
        if out_writer is None:
            annotated_video = None
        else:
            print(f"Annotated video writer initialized with codec: {selected_codec}")
    else:
        out_writer = None

    if use_ultralytics_tracking:
        tracker = None
        _reset_ultralytics_tracker(yolo_model, normalized_backend)
    else:
        # The centroid gate was tuned on 512px-wide frames; scale it so native
        # resolution does not change the effective association tolerance.
        match_scale = (native_width / 512.0) if native_width else 1.0
        tracker = build_tracker_backend(
            tracker_backend,
            embedder_gpu=_has_gpu(),
            min_hits=tracker_min_hits,
            match_distance=80.0 * max(0.25, match_scale),
        )
    yolo_device = _resolve_yolo_device()
    yolo_half = _is_cuda_device(yolo_device) and os.getenv("TVA_PIPELINE_HALF", "1").strip().lower() in {"1", "true", "yes", "on"}
    classification_votes = TrackClassificationVotes(
        custom_classes=custom_classes,
        threshold=classification_threshold,
        required_samples=classification_vote_samples,
    )
    counter = RoiEntryCounter(custom_classes, classification_votes)
    class_counts = counter.class_counts

    time_series = []
    detection_classes = list(yolo_class_names.keys())
    frame_idx = 0
    tracks = []
    last_recorded_bucket = None
    final_snapshot = None
    show_track_ids = os.getenv("TVA_ANNOTATE_TRACK_IDS", "").strip().lower() in {"1", "true", "yes", "on"}
    processing_fps = None
    last_frame_time = None

    max_retries = 10
    retry_count = 0
    sample_interval = max(1, int(time_series_interval_seconds))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    last_reported_frame = 0
    is_stream_source = _is_stream_source(video_path)

    if progress_callback:
        progress_callback(0, "Starting video analysis...")

    while True:
        if should_cancel and should_cancel():
            raise AnalysisCancelled("Analysis canceled.")

        ret, frame = cap.read()
        if not ret or frame is None or frame.size == 0:
            if not is_stream_source:
                print("Reached end of uploaded/local video file. Ending processing.")
                break
            retry_count += 1
            print(f"Failed to grab frame, retry {retry_count}/{max_retries}")
            time.sleep(1)
            if retry_count >= max_retries:
                print("Stream appears to be down. Ending processing.")
                break
            continue

        retry_count = 0
        frame_idx += 1

        frame_started_at = time.perf_counter()
        if last_frame_time is not None:
            frame_delta = frame_started_at - last_frame_time
            if frame_delta > 0:
                instant_fps = 1.0 / frame_delta
                processing_fps = (
                    instant_fps if processing_fps is None else 0.9 * processing_fps + 0.1 * instant_fps
                )
        last_frame_time = frame_started_at

        if fps > 0:
            frame_time_sec = frame_idx / fps
        else:
            frame_time_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000

        try:
            real_timestamp = start_dt + datetime.timedelta(seconds=frame_time_sec)
        except OverflowError:
            real_timestamp = datetime.datetime.now()

        if roi_polygon is None:
            # Some stream sources do not report dimensions before decode.
            native_height, native_width = frame.shape[:2]
            roi_polygon = _build_roi_polygon(roi_points, native_width, native_height)
            if tracker is not None and hasattr(tracker, "match_distance"):
                tracker.match_distance = 80.0 * max(0.25, native_width / 512.0)
            crop_scale = max(1.0, native_width / 512.0)
            effective_min_w = max(1, int(min_w * crop_scale))
            effective_min_h = max(1, int(min_h * crop_scale))

        if denoise:
            # Disabled by default and never enabled by services: NlMeans on a
            # native HD frame is an order of magnitude slower than it was on
            # the old 512x384 working frame.
            frame = cv2.fastNlMeansDenoisingColored(frame, None, 10, 10, 7, 21)

        if frame_idx % detection_interval == 0:
            if use_ultralytics_tracking:
                yolo_results = yolo_model.track(
                    frame,
                    persist=True,
                    tracker=f"{normalized_backend}.yaml",
                    imgsz=detection_imgsz,
                    verbose=False,
                    classes=detection_classes,
                    # The tracker needs to see detections below the counting
                    # threshold to bridge occlusion dips, but a floor that is
                    # too low floods dense scenes with noise tracks; the
                    # counting-grade filter re-applies on emitted boxes below.
                    conf=min(tracker_feed_conf, confidence_threshold),
                    iou=nms_iou,
                    device=yolo_device,
                    half=yolo_half,
                )
                tracks = []
                for result in yolo_results:
                    if result.boxes is None:
                        continue
                    for box in result.boxes:
                        if box.id is None:
                            continue
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        if conf < confidence_threshold or cls_id not in yolo_class_names:
                            continue
                        bx1, by1, bx2, by2 = map(int, box.xyxy[0])
                        tracks.append(TrackerTrack(int(box.id[0]), (bx1, by1, bx2, by2), confirmed=True))
            else:
                yolo_results = yolo_model(
                    frame,
                    imgsz=detection_imgsz,
                    verbose=False,
                    classes=detection_classes,
                    conf=confidence_threshold,
                    iou=nms_iou,
                    device=yolo_device,
                    half=yolo_half,
                )
                tracker_inputs = []
                for result in yolo_results:
                    for box in result.boxes:
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        if conf < confidence_threshold or cls_id not in yolo_class_names:
                            continue
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        tracker_inputs.append([[x1, y1, x2 - x1, y2 - y1], conf, cls_id])
                tracker_inputs.sort(key=lambda item: (item[0][0], item[0][1], item[0][2], item[0][3], item[2]))
                tracks = tracker.update_tracks(tracker_inputs, frame=frame)
        elif not use_ultralytics_tracking:
            tracks = tracker.update_tracks([], frame=frame)
        # else: ultralytics tracking holds the previous tracks between
        # detection frames (positions frozen, like the centroid backend).

        # Classify all qualifying crops for this detection frame in a single
        # batched forward pass. Running the classifier once per track (batch
        # size 1) inside the loop below dominated per-frame cost on busy frames.
        frame_probs = {}
        if frame_idx % detection_interval == 0:
            batch_track_ids = []
            batch_inputs = []
            for track in tracks:
                if not track.is_confirmed():
                    continue
                track_id = track.track_id
                if not counter.needs_sample(track_id):
                    continue
                x1, y1, x2, y2 = map(int, track.to_ltrb())
                # ROI membership must use the raw centroid so this pre-pass and
                # the counting loop below always agree for edge-clipped boxes.
                cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                if cv2.pointPolygonTest(roi_polygon, (cx, cy), False) < 0:
                    continue
                # Tracker boxes can drift off-frame; negative indices would
                # silently crop the wrong region via Python wraparound.
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(native_width, x2)
                y2 = min(native_height, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                # Crop from the native frame so the classifier sees real
                # pixels, not detail destroyed by a downscaled working frame.
                crop = frame[y1:y2, x1:x2]
                if crop.shape[0] < effective_min_h or crop.shape[1] < effective_min_w:
                    continue
                rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                small = cv2.resize(rgb, (224, 224))
                arr = keras_preprocess(img_to_array(small))
                batch_track_ids.append(track_id)
                batch_inputs.append(arr)

            if batch_inputs:
                batch = np.stack(batch_inputs, axis=0)
                # Direct model call skips Model.predict()'s per-call tf.data and
                # callback setup, which dominates at these tiny batch sizes.
                batch_probs = np.asarray(classifier_model(batch, training=False))
                for sample_track_id, probs in zip(batch_track_ids, batch_probs):
                    frame_probs[sample_track_id] = probs

        canvas = None
        if should_draw_annotations:
            # Draw on a canvas at the output size with scaled coordinates so
            # text stays crisp instead of being shrunk by a late downscale.
            canvas = cv2.resize(frame, (out_width, out_height))
            scale_x = out_width / float(native_width)
            scale_y = out_height / float(native_height)

        for track in tracks:
            if not track.is_confirmed():
                continue

            x1, y1, x2, y2 = map(int, track.to_ltrb())
            track_id = track.track_id
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
            now_inside = cv2.pointPolygonTest(roi_polygon, (cx, cy), False) >= 0

            counter.observe(
                track_id,
                now_inside,
                frame_idx % detection_interval == 0,
                probabilities=frame_probs.get(track_id),
            )

            if canvas is not None:
                # Only counted tracks are drawn: pending ones as a thin gray
                # box, resolved ones in their class color with a label chip.
                display_label = counter.track_labels.get(track_id)
                if display_label is not None:
                    draw_track(
                        canvas,
                        (int(x1 * scale_x), int(y1 * scale_y), int(x2 * scale_x), int(y2 * scale_y)),
                        display_label,
                        confidence=counter.track_confidences.get(track_id),
                        track_id=track_id,
                        show_track_id=show_track_ids,
                    )

        bucket_index = int(frame_time_sec // sample_interval)
        snapshot = {
            "timestamp": real_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            **class_counts.copy(),
        }
        if bucket_index != last_recorded_bucket:
            time_series.append(snapshot)
            last_recorded_bucket = bucket_index
        final_snapshot = snapshot

        if canvas is not None:
            roi_canvas = (roi_polygon * np.array([scale_x, scale_y])).astype(np.int32)
            draw_counting_zone(canvas, roi_canvas)
            draw_hud(canvas, class_counts, real_timestamp.strftime("%H:%M:%S"), fps=processing_fps)
            draw_watermark(canvas)

        if display and canvas is not None:
            cv2.imshow("Processing", canvas)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print("[INFO] 'q' pressed, exiting loop.")
                break

        if out_writer and canvas is not None:
            out_writer.write(canvas)

        if progress_callback and (frame_idx == 1 or frame_idx - last_reported_frame >= progress_report_frames):
            if total_frames > 0:
                progress_percent = min(99, int((frame_idx / total_frames) * 100))
                progress_message = f"Processed {frame_idx} of {total_frames} frames."
            else:
                progress_percent = None
                progress_message = f"Processed {frame_idx} frames."
            progress_callback(progress_percent, progress_message)
            last_reported_frame = frame_idx

    cap.release()
    if display:
        cv2.destroyAllWindows()
    if out_writer:
        out_writer.release()

    counter.finalize()

    if final_snapshot:
        final_snapshot = {**final_snapshot, **class_counts.copy()}
        if not time_series or time_series[-1] != final_snapshot:
            time_series.append(final_snapshot)

    if progress_callback:
        progress_callback(99, "Finalizing analysis results...")

    return {
        "counts": class_counts,
        "time_series": time_series,
        "annotated_video": annotated_video,
        "classification_confidence": counter.confidence_summary(),
    }
