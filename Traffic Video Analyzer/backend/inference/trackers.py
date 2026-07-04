import math

import numpy as np


class TrackerSelectionError(ValueError):
    pass


class TrackerTrack:
    def __init__(self, track_id, ltrb, confirmed=True):
        self.track_id = track_id
        self._ltrb = tuple(int(value) for value in ltrb)
        self._confirmed = confirmed

    def is_confirmed(self):
        return self._confirmed

    def to_ltrb(self):
        return self._ltrb


class DeepSortTrackerBackend:
    def __init__(self, embedder_gpu=False, n_init=2, max_age=15):
        from deep_sort_realtime.deepsort_tracker import DeepSort

        self._tracker = DeepSort(
            max_age=max_age,
            n_init=n_init,
            nms_max_overlap=1.0,
            max_cosine_distance=0.2,
            nn_budget=25,
            embedder="mobilenet",
            embedder_gpu=embedder_gpu,
        )

    def update_tracks(self, detections, frame=None):
        return self._tracker.update_tracks(detections, frame=frame)


class CentroidTrackerBackend:
    def __init__(self, max_missed=15, match_distance=80.0, min_hits=2):
        self.max_missed = max(1, int(max_missed))
        self.match_distance = float(match_distance)
        # A track must be matched on min_hits detection updates before it is
        # confirmed, so a single spurious detection never becomes a countable
        # vehicle (mirrors DeepSORT's n_init).
        self.min_hits = max(1, int(min_hits))
        self.next_track_id = 1
        self.objects = {}

    @staticmethod
    def _to_ltrb(detection):
        (x, y, w, h), _, _ = detection
        return (int(x), int(y), int(x + w), int(y + h))

    @staticmethod
    def _centroid(ltrb):
        x1, y1, x2, y2 = ltrb
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _register(self, ltrb):
        track_id = self.next_track_id
        self.next_track_id += 1
        self.objects[track_id] = {
            "ltrb": ltrb,
            "centroid": self._centroid(ltrb),
            "missed": 0,
            "hits": 1,
            "confirmed": self.min_hits <= 1,
        }

    def _unmatched_existing_ids(self, matched_ids):
        return [track_id for track_id in self.objects if track_id not in matched_ids]

    def update_tracks(self, detections, frame=None):
        del frame
        ltrb_detections = [self._to_ltrb(detection) for detection in detections]

        if not self.objects:
            for ltrb in ltrb_detections:
                self._register(ltrb)
            return self._confirmed_tracks()

        if not ltrb_detections:
            self._age_existing_objects()
            return self._confirmed_tracks()

        matches, unmatched_track_ids, unmatched_detection_indexes = self._match_detections(ltrb_detections)

        for track_id, detection_index in matches:
            ltrb = ltrb_detections[detection_index]
            self.objects[track_id]["ltrb"] = ltrb
            self.objects[track_id]["centroid"] = self._centroid(ltrb)
            self.objects[track_id]["missed"] = 0
            self.objects[track_id]["hits"] += 1
            if self.objects[track_id]["hits"] >= self.min_hits:
                self.objects[track_id]["confirmed"] = True

        for track_id in unmatched_track_ids:
            if track_id not in self.objects:
                continue
            if not self.objects[track_id]["confirmed"]:
                # A tentative track missed on a frame that had detections is
                # treated as spurious and deleted, mirroring DeepSORT's n_init
                # handling. Empty updates (no detection ran) only age tracks.
                self.objects.pop(track_id)
                continue
            self.objects[track_id]["missed"] += 1

        for detection_index in unmatched_detection_indexes:
            self._register(ltrb_detections[detection_index])

        self._purge_stale_objects()
        return self._confirmed_tracks()

    def _age_existing_objects(self):
        for track_id in list(self.objects.keys()):
            self.objects[track_id]["missed"] += 1
        self._purge_stale_objects()

    def _purge_stale_objects(self):
        for track_id in list(self.objects.keys()):
            if self.objects[track_id]["missed"] > self.max_missed:
                self.objects.pop(track_id, None)

    def _match_detections(self, ltrb_detections):
        distance_candidates = []
        detection_centroids = [self._centroid(ltrb) for ltrb in ltrb_detections]
        for track_id, payload in self.objects.items():
            for detection_index, centroid in enumerate(detection_centroids):
                distance = math.dist(payload["centroid"], centroid)
                distance_candidates.append((distance, track_id, detection_index))

        distance_candidates.sort(key=lambda item: item[0])
        matched_track_ids = set()
        matched_detection_indexes = set()
        matches = []

        for distance, track_id, detection_index in distance_candidates:
            if distance > self.match_distance:
                continue
            if track_id in matched_track_ids or detection_index in matched_detection_indexes:
                continue
            matched_track_ids.add(track_id)
            matched_detection_indexes.add(detection_index)
            matches.append((track_id, detection_index))

        unmatched_track_ids = self._unmatched_existing_ids(matched_track_ids)
        unmatched_detection_indexes = [
            detection_index
            for detection_index in range(len(ltrb_detections))
            if detection_index not in matched_detection_indexes
        ]
        return matches, unmatched_track_ids, unmatched_detection_indexes

    def _confirmed_tracks(self):
        return [
            TrackerTrack(track_id, payload["ltrb"], confirmed=payload.get("confirmed", True))
            for track_id, payload in sorted(self.objects.items())
        ]


def build_tracker_backend(name, embedder_gpu=False, min_hits=2, match_distance=80.0, max_missed=15):
    normalized = (name or "centroid").strip().lower()
    if normalized == "deepsort":
        return DeepSortTrackerBackend(embedder_gpu=embedder_gpu, n_init=min_hits, max_age=max_missed)
    if normalized in {"centroid", "simple"}:
        return CentroidTrackerBackend(max_missed=max_missed, match_distance=match_distance, min_hits=min_hits)
    raise TrackerSelectionError(f"Unsupported tracker backend: {name}")
