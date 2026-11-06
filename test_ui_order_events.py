import unittest

from chronosengine.ui.terminal_ui import (
    detect_order_events,
    get_best_spread,
)


class TestOrderEventDetection(unittest.TestCase):

    def test_fill_event_is_detected(self):
        previous = {
            "buys": [{"order_id": 1, "price": 100, "quantity": 5}],
            "sells": [{"order_id": 2, "price": 101, "quantity": 5}],
        }
        current = {
            "buys": [],
            "sells": [],
        }
        trades = [{
            "buy_order_id": 1,
            "sell_order_id": 2,
            "price": 100,
            "quantity": 5,
            "timestamp": 1000,
        }]

        events, count, spread = detect_order_events(
            previous, current, 0, trades, 1.0
        )

        self.assertEqual(count, 1)
        self.assertEqual(
            [event["type"] for event in events],
            ["FILL"],
        )
        self.assertIsNone(spread)

    def test_cancel_event_is_detected(self):
        previous = {
            "buys": [{"order_id": 10, "price": 99, "quantity": 4}],
            "sells": [],
        }
        current = {
            "buys": [],
            "sells": [],
        }

        events, count, spread = detect_order_events(
            previous, current, 0, [], None
        )

        self.assertEqual(
            [event["type"] for event in events],
            ["CANCEL"],
        )
        self.assertEqual(count, 0)

    def test_filled_order_is_not_misclassified_as_cancel(self):
        previous = {
            "buys": [{"order_id": 10, "price": 100, "quantity": 4}],
            "sells": [],
        }
        current = {
            "buys": [],
            "sells": [],
        }
        trades = [{
            "buy_order_id": 10,
            "sell_order_id": 20,
            "price": 100,
            "quantity": 4,
        }]

        events, _, _ = detect_order_events(
            previous, current, 0, trades, None
        )

        self.assertEqual(
            [event["type"] for event in events],
            ["FILL"],
        )

    def test_spread_shift_is_detected(self):
        previous = {
            "buys": [{"order_id": 1, "price": 100, "quantity": 2}],
            "sells": [{"order_id": 2, "price": 105, "quantity": 2}],
        }
        current = {
            "buys": [{"order_id": 1, "price": 101, "quantity": 2}],
            "sells": [{"order_id": 2, "price": 105, "quantity": 2}],
        }

        events, _, spread = detect_order_events(
            previous, current, 0, [], 5.0
        )

        self.assertEqual(
            [event["type"] for event in events],
            ["SPREAD"],
        )
        self.assertEqual(spread, 4.0)

    def test_initial_spread_is_not_reported_as_shift(self):
        order_book = {
            "buys": [{"order_id": 1, "price": 100, "quantity": 2}],
            "sells": [{"order_id": 2, "price": 105, "quantity": 2}],
        }

        self.assertEqual(get_best_spread(order_book), 5.0)

        events, _, spread = detect_order_events(
            None, order_book, 0, [], 5.0
        )

        self.assertEqual(events, [])
        self.assertEqual(spread, 5.0)


if __name__ == "__main__":
    unittest.main()
