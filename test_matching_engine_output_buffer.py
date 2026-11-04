import os
import tempfile
import unittest

from mmap_trade_ringbuffer import MmapTradeRingBuffer
from chronosengine.matching_engine import MatchingEngine


class TestMatchingEngineOutputBuffer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        filename = os.path.join(
            self.temp_dir.name,
            "matched_trades.dat"
        )
        self.buffer = MmapTradeRingBuffer(filename, 1)
        self.engine = MatchingEngine()
        self.engine.set_output_ring_buffer(self.buffer)

    def tearDown(self):
        self.buffer.close()
        self.temp_dir.cleanup()

    def test_buy_order_writes_fill_directly_to_output_buffer(self):
        self.engine.submit_order(101, "S", 100.0, 5, 10)
        result = self.engine.submit_order(102, "B", 105.0, 3, 20)

        trade = self.buffer.read_next()

        self.assertEqual(result["filled_quantity"], 3)
        self.assertEqual(trade["trade_id"], 1)
        self.assertEqual(trade["buy_order_id"], 102)
        self.assertEqual(trade["sell_order_id"], 101)
        self.assertEqual(trade["price"], 100.0)
        self.assertEqual(trade["quantity"], 3)
        self.assertEqual(trade["timestamp"], 20)

        # With an output buffer attached, fills are not copied into _trades.
        self.assertEqual(self.engine.get_trades(), [])

    def test_sell_order_writes_fill_directly_to_output_buffer(self):
        self.engine.submit_order(201, "B", 100.0, 5, 10)
        result = self.engine.submit_order(202, "S", 95.0, 2, 20)

        trade = self.buffer.read_next()

        self.assertEqual(result["filled_quantity"], 2)
        self.assertEqual(trade["trade_id"], 1)
        self.assertEqual(trade["buy_order_id"], 201)
        self.assertEqual(trade["sell_order_id"], 202)
        self.assertEqual(trade["price"], 100.0)
        self.assertEqual(trade["quantity"], 2)
        self.assertEqual(trade["timestamp"], 20)

    def test_full_output_buffer_does_not_mutate_maker_order(self):
        self.engine.submit_order(301, "S", 100.0, 5, 10)
        self.engine.submit_order(302, "B", 100.0, 2, 20)

        with self.assertRaises(BufferError):
            self.engine.submit_order(303, "B", 100.0, 1, 30)

        # The failed fill must not reduce the resting sell quantity.
        book = self.engine.get_order_book()
        self.assertEqual(book["sells"][0]["order_id"], 301)
        self.assertEqual(book["sells"][0]["quantity"], 3)

        # Only the first execution should be present.
        self.assertEqual(self.buffer.get_stats()["unread"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

