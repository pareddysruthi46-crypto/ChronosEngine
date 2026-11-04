import unittest

from chronosengine.ui.terminal_ui import build_latency_histogram


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
