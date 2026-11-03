import unittest

from chronosengine.latency_metrics import RollingLatencyPercentiles
from chronosengine.matching_engine import MatchingEngine


class TestRollingLatencyPercentiles(unittest.TestCase):

    def test_known_percentiles(self):
        metrics = RollingLatencyPercentiles(window_size=100)

        for value in range(1, 101):
            metrics.add_sample(value)

        result = metrics.get_percentiles()

        self.assertEqual(result["p50_latency_ns"], 50)
        self.assertEqual(result["p90_latency_ns"], 90)
        self.assertEqual(result["p99_latency_ns"], 99)
        self.assertEqual(result["p999_latency_ns"], 100)

    def test_rolling_window(self):
        metrics = RollingLatencyPercentiles(window_size=3)

        for value in [10, 20, 30, 40, 50]:
            metrics.add_sample(value)

        result = metrics.get_percentiles()

        self.assertEqual(result["latency_sample_count"], 3)
        self.assertEqual(result["p50_latency_ns"], 40)
        self.assertEqual(result["p90_latency_ns"], 50)
        self.assertEqual(result["p99_latency_ns"], 50)
        self.assertEqual(result["p999_latency_ns"], 50)

    def test_empty_window(self):
        metrics = RollingLatencyPercentiles(window_size=10)

        result = metrics.get_percentiles()

        self.assertEqual(result["p50_latency_ns"], 0)
        self.assertEqual(result["p90_latency_ns"], 0)
        self.assertEqual(result["p99_latency_ns"], 0)
        self.assertEqual(result["p999_latency_ns"], 0)
        self.assertEqual(result["latency_sample_count"], 0)

    def test_invalid_window_size(self):
        for size in [0, -1, 1.5, True]:
            with self.subTest(size=size):
                with self.assertRaises((ValueError, TypeError)):
                    RollingLatencyPercentiles(window_size=size)

    def test_negative_latency(self):
        metrics = RollingLatencyPercentiles(window_size=10)

        with self.assertRaises(ValueError):
            metrics.add_sample(-10)

    def test_matching_engine_integration(self):
        engine = MatchingEngine(latency_window_size=2)

        engine.submit_order(1, "B", 100.0, 10, 1)

        with self.assertRaises(ValueError):
            engine.submit_order(2, "X", 100.0, 10, 2)

        engine.submit_order(3, "S", 101.0, 5, 3)

        result = engine.get_latency_metrics()

        self.assertEqual(result["measured_orders"], 3)
        self.assertEqual(result["successful_orders"], 2)
        self.assertEqual(result["failed_orders"], 1)
        self.assertEqual(result["latency_window_size"], 2)
        self.assertEqual(result["latency_sample_count"], 2)

        self.assertLessEqual(
            result["p50_latency_ns"],
            result["p90_latency_ns"],
        )
        self.assertLessEqual(
            result["p90_latency_ns"],
            result["p99_latency_ns"],
        )
        self.assertLessEqual(
            result["p99_latency_ns"],
            result["p999_latency_ns"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
