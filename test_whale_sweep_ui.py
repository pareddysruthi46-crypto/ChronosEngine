import unittest

from chronosengine.ui.terminal_ui import (
    detect_order_events,
    detect_whale_sweeps,
)


class TestWhaleSweepDetection(unittest.TestCase):

    def test_buy_sweep(self):
        trades = [
            {"buy_order_id": 900, "sell_order_id": 11,
             "price": 101, "quantity": 100},
            {"buy_order_id": 900, "sell_order_id": 12,
             "price": 102, "quantity": 100},
            {"buy_order_id": 900, "sell_order_id": 13,
             "price": 103, "quantity": 100},
            {"buy_order_id": 900, "sell_order_id": 14,
             "price": 104, "quantity": 50},
        ]

        events = detect_whale_sweeps(trades)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "WHALE_BUY")
        self.assertEqual(events[0]["order_id"], 900)
        self.assertEqual(events[0]["executed_quantity"], 350)
        self.assertEqual(events[0]["levels_hit"], 4)
        self.assertEqual(
            events[0]["matched_price_levels"],
            [101, 102, 103, 104],
        )

    def test_sell_sweep(self):
        trades = [
            {"buy_order_id": 21, "sell_order_id": 901,
             "price": 104, "quantity": 100},
            {"buy_order_id": 22, "sell_order_id": 901,
             "price": 103, "quantity": 100},
            {"buy_order_id": 23, "sell_order_id": 901,
             "price": 102, "quantity": 50},
        ]

        events = detect_whale_sweeps(trades)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "WHALE_SELL")
        self.assertEqual(events[0]["order_id"], 901)
        self.assertEqual(events[0]["executed_quantity"], 250)
        self.assertEqual(events[0]["levels_hit"], 3)

    def test_same_price_fills_are_not_a_sweep(self):
        trades = [
            {"buy_order_id": 900, "sell_order_id": 11,
             "price": 101, "quantity": 40},
            {"buy_order_id": 900, "sell_order_id": 12,
             "price": 101, "quantity": 60},
        ]

        self.assertEqual(detect_whale_sweeps(trades), [])

    def test_normal_fill_is_not_a_whale_event(self):
        trades = [{
            "buy_order_id": 1,
            "sell_order_id": 2,
            "price": 100,
            "quantity": 5,
        }]

        events, _, _ = detect_order_events(
            None,
            {"buys": [], "sells": []},
            0,
            trades,
            None,
        )

        self.assertEqual(
            [event["type"] for event in events],
            ["FILL"],
        )

    def test_order_detector_appends_whale_event(self):
        trades = [
            {"buy_order_id": 900, "sell_order_id": 11,
             "price": 101, "quantity": 100},
            {"buy_order_id": 900, "sell_order_id": 12,
             "price": 102, "quantity": 50},
        ]

        events, count, _ = detect_order_events(
            None,
            {"buys": [], "sells": []},
            0,
            trades,
            None,
        )

        self.assertEqual(count, 2)
        self.assertEqual(events[-1]["type"], "WHALE_BUY")
        self.assertIn("detected_at", events[-1])


if __name__ == "__main__":
    unittest.main()
