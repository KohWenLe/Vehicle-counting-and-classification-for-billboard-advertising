import argparse
import datetime
import json
import time

from backend.inference.pipeline import process_video


def run_once(video_path, vote_samples):
    start = time.perf_counter()
    result = process_video(
        video_path,
        start_dt=datetime.datetime(2024, 7, 7, 9, 0),
        save_annotated=False,
        tracker_backend="centroid",
        classification_vote_samples=vote_samples,
    )
    elapsed = time.perf_counter() - start
    return {
        "counts": result["counts"],
        "elapsed_seconds": round(elapsed, 2),
        "time_series_points": len(result["time_series"]),
    }


def main():
    parser = argparse.ArgumentParser(description="Run repeat pipeline checks for classification voting.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--vote-samples", type=int, default=3)
    args = parser.parse_args()

    results = []
    for run_index in range(max(1, args.runs)):
        print(f"Starting run {run_index + 1}/{args.runs} with vote_samples={args.vote_samples}...")
        results.append(run_once(args.video, args.vote_samples))
        print(json.dumps(results[-1], indent=2))

    print(json.dumps({"video": args.video, "vote_samples": args.vote_samples, "runs": results}, indent=2))


if __name__ == "__main__":
    main()
