
import unittest

from chronosengine.matching_engine import MatchingEngine


class TestLatencyMetrics(unittest.TestCase):

    def test_successful_order_records_timestamps(self):
        engine = MatchingEngine()

        engine.submit_order(1, "B", 100.0, 10, 1)
        metrics = engine.get_latency_metrics()

        self.assertGreater(metrics["last_ingress_ns"], 0)
        self.assertGreaterEqual(
            metrics["last_egress_ns"],
            metrics["last_ingress_ns"],
        )
        self.assertEqual(
            metrics["last_latency_ns"],
            metrics["last_egress_ns"] - metrics["last_ingress_ns"],
        )
        self.assertEqual(metrics["measured_orders"], 1)
        self.assertEqual(metrics["successful_orders"], 1)
        self.assertEqual(metrics["failed_orders"], 0)

    def test_failed_order_is_counted(self):
        engine = MatchingEngine()

        with self.assertRaises(ValueError):
            engine.submit_order(1, "X", 100.0, 10, 1)

        metrics = engine.get_latency_metrics()

        self.assertEqual(metrics["measured_orders"], 1)
        self.assertEqual(metrics["successful_orders"], 0)
        self.assertEqual(metrics["failed_orders"], 1)

    def test_duplicate_order_is_counted_as_failure(self):
        engine = MatchingEngine()
        engine.submit_order(1, "B", 100.0, 10, 1)

        with self.assertRaises(ValueError):
            engine.submit_order(1, "S", 99.0, 5, 2)

        metrics = engine.get_latency_metrics()

        self.assertEqual(metrics["measured_orders"], 2)
        self.assertEqual(metrics["successful_orders"], 1)
        self.assertEqual(metrics["failed_orders"], 1)

    def test_insert_order_records_latency(self):
        engine = MatchingEngine()

        result = engine.insert_order(1, "B", 100.0, 10, 1)

        self.assertTrue(result)

        metrics = engine.get_latency_metrics()

        self.assertEqual(metrics["measured_orders"], 1)
        self.assertEqual(metrics["successful_orders"], 1)
        self.assertEqual(metrics["failed_orders"], 0)
        self.assertEqual(
            metrics["last_latency_ns"],
            metrics["last_egress_ns"] - metrics["last_ingress_ns"],
        )

    def test_latency_statistics(self):
        engine = MatchingEngine()

        engine.submit_order(1, "B", 100.0, 10, 1)
        engine.submit_order(2, "S", 101.0, 5, 2)

        metrics = engine.get_latency_metrics()

        self.assertEqual(metrics["measured_orders"], 2)
        self.assertEqual(metrics["successful_orders"], 2)
        self.assertEqual(metrics["failed_orders"], 0)

        self.assertGreaterEqual(
            metrics["max_latency_ns"],
            metrics["min_latency_ns"],
        )

        self.assertGreater(metrics["average_latency_ns"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
