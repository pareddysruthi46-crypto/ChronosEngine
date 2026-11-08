import unittest
from unittest.mock import patch

from chronosengine.ui.system_telemetry import (
    collect_system_health,
    get_buffer_telemetry,
    summarize_trade_counters,
)


class FakeEngine:
    def get_memory_pool_stats(self):
        return {
            "capacity": 1000,
            "available": 750,
            "in_use": 250,
        }


class FakeBuffer:
    file_size = 4096

    def get_stats(self):
        return {
            "capacity": 100,
            "unread": 25,
            "available": 75,
        }


class TestSystemTelemetry(unittest.TestCase):

    def test_trade_counters(self):
        trades = [
            {"buy_order_id": 1, "sell_order_id": 2},
            {"buy_order_id": 3, "sell_order_id": 4},
        ]

        result = summarize_trade_counters(trades)

        self.assertEqual(result["executions"], 2)
        self.assertEqual(result["buy_participations"], 2)
        self.assertEqual(result["sell_participations"], 2)

    def test_empty_trade_counters(self):
        result = summarize_trade_counters([])

        self.assertEqual(result["executions"], 0)
        self.assertEqual(result["buy_participations"], 0)
        self.assertEqual(result["sell_participations"], 0)

    def test_buffer_telemetry(self):
        result = get_buffer_telemetry(FakeBuffer())

        self.assertEqual(result["capacity"], 100)
        self.assertEqual(result["unread"], 25)
        self.assertEqual(result["available"], 75)
        self.assertEqual(result["allocated_bytes"], 4096)

    def test_missing_buffer_returns_none(self):
        self.assertIsNone(get_buffer_telemetry(None))

    def test_invalid_buffer_returns_none(self):
        self.assertIsNone(get_buffer_telemetry(object()))

    @patch(
        "chronosengine.ui.system_telemetry.psutil.cpu_percent",
        return_value=23.5,
    )
    def test_collect_system_health(self, mock_cpu):
        result = collect_system_health(
            FakeEngine(),
            [{"buy_order_id": 1, "sell_order_id": 2}],
            FakeBuffer(),
            None,
        )

        self.assertEqual(result["cpu_percent"], 23.5)
        self.assertEqual(result["memory_pool"]["in_use"], 250)
        self.assertEqual(result["order_buffer"]["unread"], 25)
        self.assertIsNone(result["trade_buffer"])
        self.assertEqual(result["trade_counters"]["executions"], 1)
        mock_cpu.assert_called_once_with(interval=None)


if __name__ == "__main__":
    unittest.main()
