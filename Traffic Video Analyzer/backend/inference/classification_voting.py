import numpy as np


class TrackClassificationVotes:
    def __init__(self, custom_classes, threshold, required_samples=3):
        self.custom_classes = list(custom_classes)
        self.threshold = float(threshold)
        self.required_samples = max(1, int(required_samples or 1))
        self._samples_by_track = {}

    def add_sample(self, track_id, probabilities):
        sample = np.asarray(probabilities, dtype=float).reshape(-1)
        self._samples_by_track.setdefault(track_id, []).append(sample)

    def sample_count(self, track_id):
        return len(self._samples_by_track.get(track_id, []))

    def has_samples(self, track_id):
        return self.sample_count(track_id) > 0

    def is_ready(self, track_id):
        return self.sample_count(track_id) >= self.required_samples

    def final_label(self, track_id):
        samples = self._samples_by_track.get(track_id, [])
        if not samples:
            return "Unclassified"

        average_probabilities = np.mean(np.stack(samples, axis=0), axis=0)
        label_index = int(np.argmax(average_probabilities))
        label_confidence = float(np.max(average_probabilities))
        if label_confidence >= self.threshold and label_index < len(self.custom_classes):
            return self.custom_classes[label_index]
        return "Unclassified"
