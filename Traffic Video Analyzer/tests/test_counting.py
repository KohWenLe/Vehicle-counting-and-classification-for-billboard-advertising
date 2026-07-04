import unittest

import numpy as np

from backend.inference.classification_voting import TrackClassificationVotes
from backend.inference.counting import RoiEntryCounter


CLASSES = ["Commercial Vehicles", "High-End Vehicles", "Motorcycle"]
CONFIDENT_HIGH_END = np.array([0.05, 0.9, 0.05])
LOW_CONFIDENCE = np.array([0.34, 0.33, 0.33])


def make_counter(required_samples=2, threshold=0.4):
    votes = TrackClassificationVotes(
        custom_classes=CLASSES,
        threshold=threshold,
        required_samples=required_samples,
    )
    return RoiEntryCounter(CLASSES, votes)


def total(counter):
    return sum(counter.class_counts.values())


class RoiEntryCounterTests(unittest.TestCase):
    def test_entry_counts_once_and_holds_unclassified(self):
        counter = make_counter()

        label = counter.observe("t1", now_inside=True, is_detection_frame=True)

        self.assertEqual(label, "Pending")
        self.assertEqual(counter.class_counts["Unclassified"], 1)
        self.assertEqual(total(counter), 1)

    def test_reentry_does_not_double_count(self):
        counter = make_counter()

        counter.observe("t1", True, True)
        counter.observe("t1", False, True)
        counter.observe("t1", True, True)

        self.assertEqual(total(counter), 1)

    def test_votes_resolve_moves_count_to_final_label(self):
        counter = make_counter(required_samples=2)

        counter.observe("t1", True, True, probabilities=CONFIDENT_HIGH_END)
        label = counter.observe("t1", True, True, probabilities=CONFIDENT_HIGH_END)

        self.assertEqual(label, "High-End Vehicles")
        self.assertEqual(counter.class_counts["High-End Vehicles"], 1)
        self.assertEqual(counter.class_counts["Unclassified"], 0)
        self.assertEqual(total(counter), 1)

    def test_fast_exit_before_votes_stays_counted_as_unclassified(self):
        counter = make_counter(required_samples=3)

        counter.observe("t1", True, True)
        label = counter.observe("t1", False, False)

        self.assertEqual(label, "Unclassified")
        self.assertEqual(counter.class_counts["Unclassified"], 1)
        self.assertEqual(total(counter), 1)

    def test_low_confidence_votes_resolve_to_unclassified(self):
        counter = make_counter(required_samples=2)

        counter.observe("t1", True, True, probabilities=LOW_CONFIDENCE)
        label = counter.observe("t1", True, True, probabilities=LOW_CONFIDENCE)

        self.assertEqual(label, "Unclassified")
        self.assertEqual(counter.class_counts["Unclassified"], 1)
        self.assertEqual(total(counter), 1)

    def test_finalize_resolves_pending_tracks(self):
        counter = make_counter(required_samples=3)

        counter.observe("t1", True, True, probabilities=CONFIDENT_HIGH_END)
        counter.finalize()

        self.assertEqual(counter.class_counts["High-End Vehicles"], 1)
        self.assertEqual(counter.class_counts["Unclassified"], 0)
        self.assertEqual(total(counter), 1)

    def test_finalize_is_idempotent_and_never_double_resolves(self):
        counter = make_counter(required_samples=1)

        counter.observe("t1", True, True, probabilities=CONFIDENT_HIGH_END)
        counter.finalize()
        counter.finalize()

        self.assertEqual(counter.class_counts["High-End Vehicles"], 1)
        self.assertEqual(counter.class_counts["Unclassified"], 0)
        self.assertEqual(total(counter), 1)

    def test_track_never_inside_roi_is_never_counted(self):
        counter = make_counter()

        counter.observe("t1", False, True)
        counter.observe("t1", False, True)
        counter.finalize()

        self.assertEqual(total(counter), 0)

    def test_no_votes_added_on_non_detection_frames(self):
        counter = make_counter(required_samples=1)

        counter.observe("t1", True, False, probabilities=CONFIDENT_HIGH_END)

        self.assertEqual(counter.votes.sample_count("t1"), 0)
        self.assertEqual(counter.class_counts["Unclassified"], 1)

    def test_resolved_track_stops_needing_samples(self):
        counter = make_counter(required_samples=1)

        self.assertTrue(counter.needs_sample("t1"))
        counter.observe("t1", True, True, probabilities=CONFIDENT_HIGH_END)
        self.assertFalse(counter.needs_sample("t1"))

    def test_total_is_monotonic_across_a_full_lifecycle(self):
        counter = make_counter(required_samples=2)
        totals = []

        for now_inside, probs in [
            (False, None),
            (True, CONFIDENT_HIGH_END),
            (True, CONFIDENT_HIGH_END),
            (False, None),
        ]:
            counter.observe("t1", now_inside, True, probabilities=probs)
            totals.append(total(counter))
        counter.finalize()
        totals.append(total(counter))

        self.assertEqual(totals, sorted(totals))
        self.assertEqual(totals[-1], 1)

    def test_multiple_tracks_count_independently(self):
        counter = make_counter(required_samples=1)

        counter.observe("t1", True, True, probabilities=CONFIDENT_HIGH_END)
        counter.observe("t2", True, True)
        counter.observe("t3", False, True)
        counter.finalize()

        self.assertEqual(counter.class_counts["High-End Vehicles"], 1)
        self.assertEqual(counter.class_counts["Unclassified"], 1)
        self.assertEqual(total(counter), 2)


if __name__ == "__main__":
    unittest.main()
