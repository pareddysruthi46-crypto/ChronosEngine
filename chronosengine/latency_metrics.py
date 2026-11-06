from collections import deque
from math import ceil


class RollingLatencyPercentiles:
    """Maintain rolling latency samples and calculate nearest-rank percentiles."""

    def __init__(self, window_size=10000):
        if isinstance(window_size, bool) or not isinstance(window_size, int):
            raise ValueError("window_size must be a positive integer")

        if window_size <= 0:
            raise ValueError("window_size must be greater than zero")

        self.window_size = window_size
        self._samples = deque(maxlen=window_size)

    def add_sample(self, latency_ns):
        if isinstance(latency_ns, bool) or not isinstance(latency_ns, int):
            raise ValueError("latency_ns must be a non-negative integer")

        if latency_ns < 0:
            raise ValueError("latency_ns cannot be negative")

        self._samples.append(latency_ns)

    def percentile(self, percentile):
        """Return a percentile using the nearest-rank method."""

        if not isinstance(percentile, (int, float)):
            raise ValueError("percentile must be numeric")

        if not 0 < percentile <= 1:
            raise ValueError("percentile must be greater than 0 and at most 1")

        if not self._samples:
            return 0

        ordered = sorted(self._samples)
        rank = ceil(percentile * len(ordered))

        return ordered[rank - 1]

    @property
    def sample_count(self):
        return len(self._samples)

    def get_samples(self):
        """Return a snapshot of the recent latency samples."""
        return tuple(self._samples)

    def get_percentiles(self):
        return {
            "p50_latency_ns": self.percentile(0.50),
            "p90_latency_ns": self.percentile(0.90),
            "p99_latency_ns": self.percentile(0.99),
            "p999_latency_ns": self.percentile(0.999),
            "latency_window_size": self.window_size,
            "latency_sample_count": self.sample_count,
        }
