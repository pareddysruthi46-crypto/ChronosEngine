
import os
import tempfile
import unittest

from chronosengine.matching_engine import MatchingEngine
from mmap_ringbuffer import MMapRingBuffer


class TestMMapConsumer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.filename = os.path.join(
            self.temp_dir.name, "orders.dat"
        )
        self.buffer = MMapRingBuffer(
            self.filename, capacity=3
        )
        self.engine = MatchingEngine()

    def tearDown(self):
        self.buffer.close()
        self.temp_dir.cleanup()

    def make_order(self, order_id, side, price, quantity=5):
        return {
            "order_id": order_id,
            "side": side,
            "price": price,
            "quantity": quantity,
            "timestamp": order_id * 100,
        }

    def test_empty_buffer(self):
        result = self.engine.consume_mmap(self.buffer)

        self.assertEqual(result, 0)
        self.assertEqual(self.buffer.unread_count, 0)

    def test_single_order_consumption(self):
        self.buffer.push(
            self.make_order(1, "B", 100)
        )

        result = self.engine.consume_mmap(self.buffer)

        self.assertEqual(result, 1)
        self.assertEqual(self.buffer.unread_count, 0)
        self.assertEqual(self.buffer.read_index, 1)

        buys = self.engine.get_order_book()["buys"]
        self.assertEqual(len(buys), 1)
        self.assertEqual(buys[0]["order_id"], 1)

    def test_buy_sell_matching(self):
        self.buffer.push(
            self.make_order(10, "S", 100)
        )
        self.buffer.push(
            self.make_order(11, "B", 105)
        )

        result = self.engine.consume_mmap(self.buffer)

        self.assertEqual(result, 2)
        self.assertEqual(self.buffer.unread_count, 0)

        trades = self.engine.get_trades()

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["buy_order_id"], 11)
        self.assertEqual(trades[0]["sell_order_id"], 10)
        self.assertEqual(trades[0]["price"], 100)
        self.assertEqual(trades[0]["quantity"], 5)

    def test_max_orders_limit(self):
        self.buffer.push(
            self.make_order(20, "B", 100)
        )
        self.buffer.push(
            self.make_order(21, "B", 101)
        )

        result = self.engine.consume_mmap(
            self.buffer, max_orders=1
        )

        self.assertEqual(result, 1)
        self.assertEqual(self.buffer.unread_count, 1)
        self.assertEqual(self.buffer.read_index, 1)

        result = self.engine.consume_mmap(self.buffer)

        self.assertEqual(result, 1)
        self.assertEqual(self.buffer.unread_count, 0)

    def test_ring_buffer_wraparound(self):
        for order_id in range(30, 32):
            self.buffer.push(
                self.make_order(order_id, "B", 100)
            )

        self.assertEqual(
            self.engine.consume_mmap(self.buffer), 2
        )

        # The write cursor and read cursor are now at index 2.
        for order_id in range(32, 35):
            self.buffer.push(
                self.make_order(order_id, "B", 100)
            )

        result = self.engine.consume_mmap(self.buffer)

        self.assertEqual(result, 3)
        self.assertEqual(self.buffer.unread_count, 0)

        buys = self.engine.get_order_book()["buys"]
        consumed_ids = {
            order["order_id"] for order in buys
        }

        self.assertEqual(
            consumed_ids, {30, 31, 32, 33, 34}
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
