import logging
import unittest

from buffer_watermarks import BufferWatermarkMonitor


class TestBufferWatermarkMonitor(unittest.TestCase):

    def setUp(self):
        self.monitor = BufferWatermarkMonitor("test")

    def test_status_thresholds(self):
        self.assertEqual(self.monitor.status(14, 20), "NORMAL")
        self.assertEqual(self.monitor.status(15, 20), "WARNING")
        self.assertEqual(self.monitor.status(18, 20), "CRITICAL")
        self.assertEqual(self.monitor.status(20, 20), "FULL")

    def test_consumer_lag_metrics(self):
        metrics = self.monitor.update(15, 20)

        self.assertEqual(metrics["watermark"], "WARNING")
        self.assertEqual(metrics["consumer_lag"], 15)
        self.assertEqual(metrics["consumer_lag_percent"], 75.0)

    def test_logs_each_upward_threshold(self):
        with self.assertLogs("chronosengine.buffer", level="WARNING") as captured:
            self.monitor.update(15, 20)
            self.monitor.update(18, 20)
            self.monitor.update(20, 20)

        self.assertEqual(len(captured.records), 3)
        self.assertEqual(
            [record.levelno for record in captured.records],
            [logging.WARNING, logging.ERROR, logging.CRITICAL],
        )

    def test_does_not_repeat_alert_at_same_level(self):
        with self.assertLogs("chronosengine.buffer", level="WARNING") as captured:
            self.monitor.update(15, 20)
            self.monitor.update(16, 20)
            self.monitor.update(17, 20)

        self.assertEqual(len(captured.records), 1)

    def test_recovery_allows_alert_again(self):
        with self.assertLogs("chronosengine.buffer", level="WARNING") as captured:
            self.monitor.update(15, 20)
            self.monitor.update(10, 20)
            self.monitor.update(15, 20)

        self.assertEqual(len(captured.records), 2)


if __name__ == "__main__":
    unittest.main()
