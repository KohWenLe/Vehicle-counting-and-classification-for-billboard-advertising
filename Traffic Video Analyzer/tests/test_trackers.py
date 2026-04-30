import unittest

from backend.inference.trackers import CentroidTrackerBackend, TrackerSelectionError, build_tracker_backend


class CentroidTrackerTests(unittest.TestCase):
    def test_centroid_tracker_reuses_track_ids_for_nearby_boxes(self):
        tracker = CentroidTrackerBackend(max_missed=2, match_distance=50)

        first_tracks = tracker.update_tracks([[[10, 10, 20, 20], 0.9, 2]], frame=None)
        second_tracks = tracker.update_tracks([[[15, 12, 20, 20], 0.9, 2]], frame=None)

        self.assertEqual(len(first_tracks), 1)
        self.assertEqual(len(second_tracks), 1)
        self.assertEqual(first_tracks[0].track_id, second_tracks[0].track_id)

    def test_centroid_tracker_registers_new_track_for_far_detection(self):
        tracker = CentroidTrackerBackend(max_missed=2, match_distance=20)

        first_tracks = tracker.update_tracks([[[10, 10, 20, 20], 0.9, 2]], frame=None)
        second_tracks = tracker.update_tracks([[[150, 150, 20, 20], 0.9, 2]], frame=None)

        self.assertEqual(len(first_tracks), 1)
        self.assertEqual(len(second_tracks), 2)
        self.assertNotEqual(first_tracks[0].track_id, second_tracks[-1].track_id)

    def test_build_tracker_backend_supports_centroid_aliases(self):
        self.assertIsInstance(build_tracker_backend("centroid"), CentroidTrackerBackend)
        self.assertIsInstance(build_tracker_backend("simple"), CentroidTrackerBackend)

    def test_build_tracker_backend_rejects_unknown_name(self):
        with self.assertRaises(TrackerSelectionError):
            build_tracker_backend("unknown")


if __name__ == "__main__":
    unittest.main()
