
import unittest

from chronosengine.ui.terminal_ui import (
    build_latency_histogram,
    count_sla_breaches,
)


class TestLatencyHistogram(unittest.TestCase):

    def test_empty_samples(self):
        self.assertEqual(build_latency_histogram([]), [])

    def test_histogram_has_five_buckets(self):
        samples = list(range(1, 101))

        result = build_latency_histogram(samples)

        self.assertEqual(len(result), 5)
        self.assertEqual(
            sum(bucket["count"] for bucket in result),
            100,
        )

    def test_histogram_contains_ascii_bars(self):
        samples = [10, 20, 30, 40, 50]

        result = build_latency_histogram(samples)

        self.assertTrue(
            all("#" in bucket["bar"] for bucket in result)
        )

    def test_invalid_samples(self):
        with self.assertRaises(ValueError):
            build_latency_histogram([-10, 20])

    def test_invalid_bucket_count(self):
        with self.assertRaises(ValueError):
            build_latency_histogram([10, 20], bucket_count=0)

    def test_single_sample(self):
        result = build_latency_histogram([100])

        self.assertEqual(len(result), 5)
        self.assertEqual(
            sum(bucket["count"] for bucket in result),
            1,
        )


class TestSLABreachCounter(unittest.TestCase):

    def test_no_breaches_below_threshold(self):
        samples = [10000, 20000, 30000]

        self.assertEqual(
            count_sla_breaches(samples),
            0,
        )

    def test_exactly_50_microseconds_is_not_breach(self):
        samples = [50000]

        self.assertEqual(
            count_sla_breaches(samples),
            0,
        )

    def test_latency_above_threshold_is_breach(self):
        samples = [50001, 75000, 100000]

        self.assertEqual(
            count_sla_breaches(samples),
            3,
        )

    def test_mixed_latency_samples(self):
        samples = [10000, 50000, 50001, 75000, 20000]

        self.assertEqual(
            count_sla_breaches(samples),
            2,
        )

    def test_empty_samples(self):
        self.assertEqual(
            count_sla_breaches([]),
            0,
        )

    def test_invalid_samples(self):
        with self.assertRaises(ValueError):
            count_sla_breaches([-100])

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):
            count_sla_breaches([10000], -1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
