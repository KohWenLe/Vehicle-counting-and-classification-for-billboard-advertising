import unittest


class AnalyzeResultsTests(unittest.TestCase):
    def test_analysis_module_keeps_expected_public_surface_after_package_move(self):
        import analysis

        self.assertTrue(hasattr(analysis, "CUSTOM_CLASSES"))
        self.assertTrue(hasattr(analysis, "analyze_results"))

    def test_peak_hour_uses_incremental_counts_and_returns_recommendations(self):
        from analysis import analyze_results

        time_series = [
            {
                "timestamp": "2024-07-07 09:00:00",
                "Commercial Vehicles": 1,
                "High-End Vehicles": 0,
                "Low-End Vehicles": 0,
                "Mid-Range Vehicles": 0,
                "Motorcycle": 0,
                "Unclassified": 0,
            },
            {
                "timestamp": "2024-07-07 09:05:00",
                "Commercial Vehicles": 3,
                "High-End Vehicles": 0,
                "Low-End Vehicles": 0,
                "Mid-Range Vehicles": 0,
                "Motorcycle": 0,
                "Unclassified": 0,
            },
            {
                "timestamp": "2024-07-07 10:00:00",
                "Commercial Vehicles": 3,
                "High-End Vehicles": 2,
                "Low-End Vehicles": 0,
                "Mid-Range Vehicles": 1,
                "Motorcycle": 0,
                "Unclassified": 0,
            },
        ]
        class_counts = {
            "Commercial Vehicles": 3,
            "High-End Vehicles": 2,
            "Low-End Vehicles": 0,
            "Mid-Range Vehicles": 1,
            "Motorcycle": 0,
            "Unclassified": 0,
        }

        result = analyze_results(time_series, class_counts)

        self.assertEqual(result["peak"], {"hour": 9, "count": 3})
        self.assertTrue(result["recommendations"])
        self.assertIn("Commercial Vehicles", result["recommendations"][0])


if __name__ == "__main__":
    unittest.main()
