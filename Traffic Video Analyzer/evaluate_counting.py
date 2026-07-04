import argparse
import datetime
import json
import os
import re
import time

import cv2

from backend.inference.pipeline import _get_cached_models, process_video


GROUND_TRUTH_PATTERN = re.compile(r"(\d+)\s*vehicles", re.IGNORECASE)


def ground_truth_from_filename(video_path):
    match = GROUND_TRUTH_PATTERN.search(os.path.basename(video_path))
    return int(match.group(1)) if match else None


def video_frame_count(video_path):
    cap = cv2.VideoCapture(video_path)
    try:
        return int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        cap.release()


def evaluate_video(video_path, tracker_backend, confidence_threshold, detection_interval, vote_samples):
    total_frames = video_frame_count(video_path)
    start = time.perf_counter()
    result = process_video(
        video_path,
        start_dt=datetime.datetime(2024, 7, 7, 9, 0),
        save_annotated=False,
        tracker_backend=tracker_backend,
        confidence_threshold=confidence_threshold,
        detection_interval=detection_interval,
        classification_vote_samples=vote_samples,
    )
    elapsed = time.perf_counter() - start

    counts = result["counts"]
    system_count = sum(counts.values())
    ground_truth = ground_truth_from_filename(video_path)
    accuracy_percent = None
    if ground_truth:
        accuracy_percent = round(max(0.0, 1.0 - abs(system_count - ground_truth) / ground_truth) * 100, 2)

    return {
        "video": os.path.basename(video_path),
        "ground_truth": ground_truth,
        "system_count": system_count,
        "counting_accuracy_percent": accuracy_percent,
        "counts": counts,
        "total_frames": total_frames,
        "elapsed_seconds": round(elapsed, 2),
        "average_fps": round(total_frames / elapsed, 2) if elapsed > 0 else None,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate counting accuracy and FPS against labeled clips (ground truth parsed from '<N>vehicles' in the filename)."
    )
    parser.add_argument(
        "--videos",
        nargs="+",
        default=["cam1_46vehicles_passed.mp4", "cam2_53vehicles_passed.mp4"],
    )
    parser.add_argument("--tracker", default="centroid")
    parser.add_argument("--conf", type=float, default=0.5)
    parser.add_argument("--detection-interval", type=int, default=2)
    parser.add_argument("--vote-samples", type=int, default=3)
    parser.add_argument("--label", default="unlabeled", help="Config name recorded in the output JSON.")
    parser.add_argument("--json-out", default=None, help="Optional path to write the full results JSON.")
    args = parser.parse_args()

    # Load models before the timed runs so the first video's FPS does not
    # absorb the one-time YOLO/Keras load. Paths match process_video defaults.
    print("Warming model cache (excluded from FPS timing)...")
    _get_cached_models("yolo11n.pt", "mobilenetv3_original.keras")

    per_video = []
    for video_path in args.videos:
        if not os.path.exists(video_path):
            print(f"Skipping missing video: {video_path}")
            continue
        print(f"Evaluating {video_path} (tracker={args.tracker}, conf={args.conf}, interval={args.detection_interval})...")
        per_video.append(
            evaluate_video(video_path, args.tracker, args.conf, args.detection_interval, args.vote_samples)
        )
        print(json.dumps(per_video[-1], indent=2))

    accuracies = [entry["counting_accuracy_percent"] for entry in per_video if entry["counting_accuracy_percent"] is not None]
    fps_values = [entry["average_fps"] for entry in per_video if entry["average_fps"]]
    summary = {
        "label": args.label,
        "tracker": args.tracker,
        "confidence_threshold": args.conf,
        "detection_interval": args.detection_interval,
        "vote_samples": args.vote_samples,
        "macro_average_accuracy_percent": round(sum(accuracies) / len(accuracies), 2) if accuracies else None,
        "average_fps": round(sum(fps_values) / len(fps_values), 2) if fps_values else None,
        "videos": per_video,
    }
    print(json.dumps(summary, indent=2))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
        print(f"Wrote results to {args.json_out}")


if __name__ == "__main__":
    main()
