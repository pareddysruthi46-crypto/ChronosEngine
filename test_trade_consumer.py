import json
import os
import tempfile
import unittest

from chronosengine.trade_consumer import (
    MatchedTradeConsumer,
    publish_new_engine_trades,
)

from chronosengine.matching_engine import MatchingEngine


def make_trade(number):
    return {
        "buy_order_id": number,
        "sell_order_id": number + 1000,
        "price": 100.0 + number,
        "quantity": 10,
        "timestamp": 1_700_000_000_000 + number,
    }


class FakeEngine:
    def __init__(self):
        self.trades = []

    def get_trades(self):
        return self.trades


class TestMatchedTradeConsumer(unittest.TestCase):

    def test_background_worker_persists_trades(self):
        """Check that the worker saves multiple trades."""
        with tempfile.TemporaryDirectory() as folder:
            output = os.path.join(folder, "trades.jsonl")

            consumer = MatchedTradeConsumer(
                output_file=output,
                batch_size=2,
            )

            trades = [
                make_trade(i)
                for i in range(1, 6)
            ]

            consumer.start()

            try:
                consumer.submit_many(trades)
            finally:
                consumer.stop()

            with open(output, encoding="utf-8") as file:
                saved = [
                    json.loads(line)
                    for line in file
                ]

            self.assertEqual(saved, trades)
            self.assertEqual(len(saved), 5)

    def test_engine_trade_publishing_only_sends_new_trades(self):
        """Check that previously published trades are not duplicated."""
        with tempfile.TemporaryDirectory() as folder:
            output = os.path.join(folder, "trades.jsonl")

            engine = FakeEngine()
            consumer = MatchedTradeConsumer(
                output_file=output
            )

            engine.trades = [
                make_trade(1),
                make_trade(2),
            ]

            consumer.start()

            try:
                count = publish_new_engine_trades(
                    engine,
                    consumer,
                    0,
                )

                engine.trades.append(make_trade(3))

                count = publish_new_engine_trades(
                    engine,
                    consumer,
                    count,
                )

            finally:
                consumer.stop()

            with open(output, encoding="utf-8") as file:
                saved = [
                    json.loads(line)
                    for line in file
                ]

            self.assertEqual(
                saved,
                [
                    make_trade(1),
                    make_trade(2),
                    make_trade(3),
                ],
            )

            self.assertEqual(count, 3)

    def test_invalid_trade_is_rejected(self):
        """Check that incomplete trade records are rejected."""
        with tempfile.TemporaryDirectory() as folder:
            output = os.path.join(folder, "trades.jsonl")

            consumer = MatchedTradeConsumer(
                output_file=output
            )

            consumer.start()

            try:
                with self.assertRaises(ValueError):
                    consumer.submit({
                        "buy_order_id": 1,
                        "price": 100.0,
                    })

            finally:
                consumer.stop()

    def test_invalid_batch_size_is_rejected(self):
        """Check that batch size must be positive."""
        with self.assertRaises(ValueError):
            MatchedTradeConsumer(batch_size=0)

    def test_actual_matching_engine_trades_are_persisted(self):
        """Check integration with the real compiled matching engine."""
        with tempfile.TemporaryDirectory() as folder:
            output = os.path.join(
                folder,
                "engine_trades.jsonl",
            )

            engine = MatchingEngine()

            consumer = MatchedTradeConsumer(
                output_file=output,
                batch_size=2,
            )

            consumer.start()

            try:
                buy_result = engine.submit_order(
                    1,
                    "B",
                    100.0,
                    10,
                    1000000001,
                )

                sell_result = engine.submit_order(
                    2,
                    "S",
                    100.0,
                    10,
                    1000000002,
                )

                last_count = publish_new_engine_trades(
                    engine,
                    consumer,
                    0,
                )

            finally:
                consumer.stop()

            with open(output, encoding="utf-8") as file:
                saved = [
                    json.loads(line)
                    for line in file
                ]

            self.assertEqual(
                buy_result["filled_quantity"],
                0,
            )

            self.assertEqual(
                sell_result["filled_quantity"],
                10,
            )

            self.assertEqual(last_count, 1)
            self.assertEqual(len(saved), 1)

            self.assertEqual(saved[0]["buy_order_id"], 1)
            self.assertEqual(saved[0]["sell_order_id"], 2)
            self.assertEqual(saved[0]["price"], 100.0)
            self.assertEqual(saved[0]["quantity"], 10)
            self.assertEqual(saved[0]["timestamp"], 1000000002)


if __name__ == "__main__":
    unittest.main(verbosity=2)