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

        # The far detection gets a fresh id; the unmatched tentative first
        # track is purged (DeepSORT-style n_init), so only the new one remains.
        self.assertEqual(len(first_tracks), 1)
        self.assertEqual(len(second_tracks), 1)
        self.assertNotEqual(first_tracks[0].track_id, second_tracks[0].track_id)

    def test_centroid_track_unconfirmed_until_min_hits(self):
        tracker = CentroidTrackerBackend(max_missed=2, match_distance=50, min_hits=2)

        first_tracks = tracker.update_tracks([[[10, 10, 20, 20], 0.9, 2]], frame=None)
        self.assertFalse(first_tracks[0].is_confirmed())

        second_tracks = tracker.update_tracks([[[15, 12, 20, 20], 0.9, 2]], frame=None)
        self.assertTrue(second_tracks[0].is_confirmed())

    def test_centroid_track_stays_confirmed_while_missed(self):
        tracker = CentroidTrackerBackend(max_missed=3, match_distance=50, min_hits=2)

        tracker.update_tracks([[[10, 10, 20, 20], 0.9, 2]], frame=None)
        tracker.update_tracks([[[15, 12, 20, 20], 0.9, 2]], frame=None)
        missed_tracks = tracker.update_tracks([], frame=None)

        self.assertEqual(len(missed_tracks), 1)
        self.assertTrue(missed_tracks[0].is_confirmed())

    def test_tentative_track_purged_when_missed_on_detection_frame(self):
        tracker = CentroidTrackerBackend(max_missed=5, match_distance=20, min_hits=2)

        tracker.update_tracks([[[10, 10, 20, 20], 0.9, 2]], frame=None)
        # A frame with detections that do not match the tentative track kills it.
        tracks = tracker.update_tracks([[[200, 200, 20, 20], 0.9, 2]], frame=None)

        remaining_ids = {track.track_id for track in tracks}
        self.assertNotIn(1, remaining_ids)

    def test_tentative_track_survives_empty_updates(self):
        tracker = CentroidTrackerBackend(max_missed=5, match_distance=50, min_hits=2)

        tracker.update_tracks([[[10, 10, 20, 20], 0.9, 2]], frame=None)
        # Empty update = no detection ran this frame (detection_interval skip).
        tracker.update_tracks([], frame=None)
        tracks = tracker.update_tracks([[[15, 12, 20, 20], 0.9, 2]], frame=None)

        self.assertEqual(len(tracks), 1)
        self.assertTrue(tracks[0].is_confirmed())

    def test_centroid_min_hits_one_confirms_immediately(self):
        tracker = CentroidTrackerBackend(max_missed=2, match_distance=50, min_hits=1)

        first_tracks = tracker.update_tracks([[[10, 10, 20, 20], 0.9, 2]], frame=None)
        self.assertTrue(first_tracks[0].is_confirmed())

    def test_build_tracker_backend_supports_centroid_aliases(self):
        self.assertIsInstance(build_tracker_backend("centroid"), CentroidTrackerBackend)
        self.assertIsInstance(build_tracker_backend("simple"), CentroidTrackerBackend)

    def test_build_tracker_backend_forwards_centroid_tuning(self):
        tracker = build_tracker_backend("centroid", min_hits=3, match_distance=25.0, max_missed=7)
        self.assertEqual(tracker.min_hits, 3)
        self.assertEqual(tracker.match_distance, 25.0)
        self.assertEqual(tracker.max_missed, 7)

    def test_build_tracker_backend_rejects_unknown_name(self):
        with self.assertRaises(TrackerSelectionError):
            build_tracker_backend("unknown")


if __name__ == "__main__":
    unittest.main()
