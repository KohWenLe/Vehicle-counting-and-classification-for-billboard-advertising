import argparse
import time

import cv2
import numpy as np
from ultralytics import YOLO

from backend.inference.trackers import build_tracker_backend


YOLO_CLASS_IDS = [2, 3, 5, 7]


def parse_resize_dim(raw_value):
    normalized = str(raw_value).lower().replace("x", ",")
    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    if len(parts) != 2:
        raise ValueError("resize must look like 512x384 or 512,384")
    return (int(parts[0]), int(parts[1]))


def collect_video_detections(video_path, resize_dim, model_path, confidence_threshold, max_frames):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source {video_path}")

    yolo_model = YOLO(model_path)
    frames = []
    detections_by_frame = []
    detection_time_seconds = 0.0
    frame_count = 0

    while frame_count < max_frames:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        frame_count += 1
        frame_resized = cv2.resize(frame, resize_dim)

        start_time = time.perf_counter()
        yolo_results = yolo_model(frame_resized, verbose=False, classes=YOLO_CLASS_IDS)
        detection_time_seconds += time.perf_counter() - start_time

        detections = []
        for result in yolo_results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                if conf < confidence_threshold:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append([[x1, y1, x2 - x1, y2 - y1], conf, cls_id])

        frames.append(frame_resized)
        detections_by_frame.append(detections)

    cap.release()
    return {
        "frames": frames,
        "detections_by_frame": detections_by_frame,
        "frame_count": len(frames),
        "detection_time_seconds": detection_time_seconds,
    }


def generate_synthetic_sequence(frame_count, resize_dim, detections_per_frame):
    width, height = resize_dim
    frames = []
    detections_by_frame = []

    base_boxes = []
    for index in range(detections_per_frame):
        base_boxes.append(
            {
                "x": 40 + index * 70,
                "y": 60 + (index % 3) * 45,
                "w": 70,
                "h": 42,
                "dx": 2 + (index % 4),
                "dy": 1 + (index % 2),
            }
        )

    for frame_index in range(frame_count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        detections = []
        for box_index, box in enumerate(base_boxes):
            x = int((box["x"] + frame_index * box["dx"]) % max(1, width - box["w"] - 5))
            y = int((box["y"] + frame_index * box["dy"]) % max(1, height - box["h"] - 5))
            color = (50 + box_index * 20, 180, 90 + box_index * 10)
            cv2.rectangle(frame, (x, y), (x + box["w"], y + box["h"]), color, -1)
            detections.append([[x, y, box["w"], box["h"]], 0.95, 2])
        frames.append(frame)
        detections_by_frame.append(detections)

    return {
        "frames": frames,
        "detections_by_frame": detections_by_frame,
        "frame_count": len(frames),
        "detection_time_seconds": 0.0,
    }


def benchmark_tracker(name, frames, detections_by_frame):
    tracker = build_tracker_backend(name, embedder_gpu=False)
    start_time = time.perf_counter()
    confirmed_track_observations = 0
    final_active_tracks = 0

    for frame, detections in zip(frames, detections_by_frame):
        tracks = tracker.update_tracks(detections, frame=frame)
        confirmed = [track for track in tracks if track.is_confirmed()]
        confirmed_track_observations += len(confirmed)
        final_active_tracks = len(confirmed)

    elapsed = time.perf_counter() - start_time
    frame_count = len(frames) or 1
    return {
        "tracker": name,
        "elapsed_seconds": elapsed,
        "frames_per_second": frame_count / elapsed if elapsed > 0 else float("inf"),
        "milliseconds_per_frame": (elapsed / frame_count) * 1000.0,
        "confirmed_track_observations": confirmed_track_observations,
        "final_active_tracks": final_active_tracks,
    }


def print_report(source_label, sequence_summary, tracker_results):
    print(f"Tracker benchmark source: {source_label}")
    print(f"Frames replayed: {sequence_summary['frame_count']}")
    if sequence_summary["detection_time_seconds"] > 0:
        detection_fps = sequence_summary["frame_count"] / sequence_summary["detection_time_seconds"]
        print(
            "YOLO detection collection: "
            f"{sequence_summary['detection_time_seconds']:.3f}s total "
            f"({detection_fps:.2f} FPS)"
        )
    print("")

    for result in tracker_results:
        print(f"Tracker: {result['tracker']}")
        print(f"  Tracking time: {result['elapsed_seconds']:.4f}s")
        print(f"  Tracking FPS: {result['frames_per_second']:.2f}")
        print(f"  ms/frame: {result['milliseconds_per_frame']:.3f}")
        print(f"  Confirmed track observations: {result['confirmed_track_observations']}")
        print(f"  Final active tracks: {result['final_active_tracks']}")
        print("")

    if len(tracker_results) >= 2:
        baseline = tracker_results[0]
        contender = tracker_results[1]
        speedup = (
            contender["frames_per_second"] / baseline["frames_per_second"]
            if baseline["frames_per_second"] > 0
            else float("inf")
        )
        print(
            f"{contender['tracker']} vs {baseline['tracker']}: "
            f"{speedup:.2f}x tracking throughput"
        )


def main():
    parser = argparse.ArgumentParser(description="Benchmark DeepSORT against a lighter tracker backend.")
    parser.add_argument("--video", help="Path to a benchmark video. Omit to use synthetic detections.")
    parser.add_argument("--resize", default="512x384", help="Resize target such as 512x384.")
    parser.add_argument("--model-path", default="yolo11n.pt", help="YOLO model path for video-mode detection collection.")
    parser.add_argument("--confidence-threshold", type=float, default=0.4, help="Minimum YOLO detection confidence.")
    parser.add_argument("--frames", type=int, default=180, help="Maximum frames to benchmark.")
    parser.add_argument(
        "--trackers",
        default="deepsort,centroid",
        help="Comma-separated tracker backends to benchmark. Example: deepsort,centroid",
    )
    parser.add_argument(
        "--synthetic-detections",
        type=int,
        default=8,
        help="How many synthetic detections to generate per frame when no video is provided.",
    )
    args = parser.parse_args()

    resize_dim = parse_resize_dim(args.resize)
    tracker_names = [name.strip() for name in args.trackers.split(",") if name.strip()]
    if not tracker_names:
        raise ValueError("At least one tracker backend must be supplied.")

    if args.video:
        sequence_summary = collect_video_detections(
            video_path=args.video,
            resize_dim=resize_dim,
            model_path=args.model_path,
            confidence_threshold=args.confidence_threshold,
            max_frames=max(1, args.frames),
        )
        source_label = args.video
    else:
        sequence_summary = generate_synthetic_sequence(
            frame_count=max(1, args.frames),
            resize_dim=resize_dim,
            detections_per_frame=max(1, args.synthetic_detections),
        )
        source_label = "synthetic"

    tracker_results = [
        benchmark_tracker(name, sequence_summary["frames"], sequence_summary["detections_by_frame"])
        for name in tracker_names
    ]
    print_report(source_label, sequence_summary, tracker_results)


if __name__ == "__main__":
    main()
