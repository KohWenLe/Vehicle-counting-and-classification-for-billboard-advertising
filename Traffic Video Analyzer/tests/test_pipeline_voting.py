import unittest

import numpy as np

from backend.inference.classification_voting import TrackClassificationVotes


class TrackClassificationVotesTests(unittest.TestCase):
    def test_vote_uses_average_probability_across_samples(self):
        votes = TrackClassificationVotes(
            custom_classes=["Commercial Vehicles", "High-End Vehicles", "Low-End Vehicles"],
            threshold=0.4,
            required_samples=3,
        )

        votes.add_sample(7, np.array([0.20, 0.39, 0.10]))
        votes.add_sample(7, np.array([0.10, 0.45, 0.20]))
        votes.add_sample(7, np.array([0.10, 0.50, 0.20]))

        self.assertTrue(votes.is_ready(7))
        self.assertEqual(votes.final_label(7), "High-End Vehicles")

    def test_vote_keeps_low_confidence_tracks_unclassified(self):
        votes = TrackClassificationVotes(
            custom_classes=["Commercial Vehicles", "High-End Vehicles", "Low-End Vehicles"],
            threshold=0.4,
            required_samples=2,
        )

        votes.add_sample(11, np.array([0.20, 0.35, 0.30]))
        votes.add_sample(11, np.array([0.25, 0.34, 0.28]))

        self.assertTrue(votes.is_ready(11))
        self.assertEqual(votes.final_label(11), "Unclassified")

    def test_single_sample_mode_preserves_existing_classification_behavior(self):
        votes = TrackClassificationVotes(
            custom_classes=["Commercial Vehicles", "High-End Vehicles"],
            threshold=0.4,
            required_samples=1,
        )

        votes.add_sample(3, np.array([0.30, 0.60]))

        self.assertTrue(votes.is_ready(3))
        self.assertEqual(votes.final_label(3), "High-End Vehicles")


if __name__ == "__main__":
    unittest.main()
