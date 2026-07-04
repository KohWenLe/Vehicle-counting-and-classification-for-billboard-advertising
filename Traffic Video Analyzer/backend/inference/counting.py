"""Entry-based ROI counting state machine (methodology report section 3.5).

A confirmed track is counted the moment its centroid enters the ROI. The count
is held under the unclassified label until classification votes resolve, then
moved to the voted class. Totals are therefore never gated on classification
readiness; per-class values may dip by one when a pending label resolves, but
the sum across classes never decreases.

This module is deliberately free of cv2/tensorflow imports so the counting
logic can be unit-tested without model weights or video decoding.
"""


class RoiEntryCounter:
    PENDING_LABEL = "Pending"

    def __init__(self, custom_classes, votes, unclassified_label="Unclassified"):
        self.votes = votes
        self.unclassified_label = unclassified_label
        self.class_counts = {name: 0 for name in custom_classes}
        self.class_counts.setdefault(unclassified_label, 0)
        self.track_labels = {}
        self._memory = {}

    def needs_sample(self, track_id):
        mem = self._memory.get(track_id)
        return not (mem and mem["label_resolved"])

    def observe(self, track_id, now_inside, is_detection_frame, probabilities=None):
        """Advance one track by one frame; returns the label to display."""
        mem = self._memory.get(track_id) or {"inside_roi": False, "counted": False, "label_resolved": False}
        was_inside = mem["inside_roi"]
        counted = mem["counted"]
        label_resolved = mem["label_resolved"]

        if now_inside and not was_inside and not counted:
            counted = True
            self._count_entry(track_id)

        if counted and not label_resolved:
            if now_inside and is_detection_frame:
                if probabilities is not None:
                    self.votes.add_sample(track_id, probabilities)
                if self.votes.is_ready(track_id):
                    self._resolve(track_id)
                    label_resolved = True
            elif was_inside and not now_inside:
                self._resolve(track_id)
                label_resolved = True

        self._memory[track_id] = {
            "inside_roi": now_inside,
            "counted": counted,
            "label_resolved": label_resolved,
        }
        return self.track_labels.get(track_id, self.unclassified_label)

    def finalize(self):
        """Resolve every counted-but-pending track at end of video/stream."""
        for track_id, mem in self._memory.items():
            if mem["counted"] and not mem["label_resolved"]:
                self._resolve(track_id)
                mem["label_resolved"] = True

    def _count_entry(self, track_id):
        self.class_counts[self.unclassified_label] += 1
        self.track_labels[track_id] = self.PENDING_LABEL

    def _resolve(self, track_id):
        cls_label = self.votes.final_label(track_id)
        if cls_label != self.unclassified_label:
            self.class_counts[self.unclassified_label] -= 1
            self.class_counts[cls_label] += 1
        self.track_labels[track_id] = cls_label
        return cls_label
