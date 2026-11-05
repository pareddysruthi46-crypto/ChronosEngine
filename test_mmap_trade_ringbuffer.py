
import os
import tempfile
import unittest

from mmap_trade_ringbuffer import (
    MmapTradeRingBuffer,
    POISON_PILL
)


class TestMmapTradeRingBuffer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.filename = os.path.join(
            self.temp_dir.name,
            "matched_trades.dat"
        )
        self.buffer = MmapTradeRingBuffer(self.filename, 3)

    def tearDown(self):
        self.buffer.close()
        self.temp_dir.cleanup()

    def add_trade(self, trade_id):
        return self.buffer.push_trade(
            trade_id,
            100 + trade_id,
            200 + trade_id,
            125.50 + trade_id,
            5,
            1720000000000 + trade_id
        )

    def test_initial_state(self):
        stats = self.buffer.get_stats()

        self.assertEqual(stats["capacity"], 3)
        self.assertEqual(stats["unread"], 0)
        self.assertEqual(stats["available"], 3)
        self.assertFalse(stats["is_shutdown"])

    def test_push_and_read_trade(self):
        self.add_trade(1)

        trade = self.buffer.read_next()

        self.assertEqual(trade["trade_id"], 1)
        self.assertEqual(trade["buy_order_id"], 101)
        self.assertEqual(trade["sell_order_id"], 201)
        self.assertEqual(trade["quantity"], 5)

    def test_full_buffer_rejects_new_trade(self):
        self.add_trade(1)
        self.add_trade(2)
        self.add_trade(3)

        with self.assertRaises(BufferError):
            self.add_trade(4)

        self.assertEqual(self.buffer.get_stats()["unread"], 3)

    def test_wraparound(self):
        self.add_trade(1)
        self.add_trade(2)
        self.add_trade(3)

        self.assertEqual(
            self.buffer.read_next()["trade_id"], 1
        )

        self.add_trade(4)

        self.assertEqual(
            self.buffer.read_next()["trade_id"], 2
        )
        self.assertEqual(
            self.buffer.read_next()["trade_id"], 3
        )
        self.assertEqual(
            self.buffer.read_next()["trade_id"], 4
        )

    def test_zero_copy_view(self):
        self.add_trade(10)

        view = self.buffer.read_next_view()

        self.assertIsNotNone(view)
        self.assertIsInstance(view, memoryview)
        self.assertEqual(len(view), 44)

        view.release()
        self.buffer.consume()

        self.assertEqual(self.buffer.get_stats()["unread"], 0)

    def test_empty_read(self):
        self.assertIsNone(self.buffer.read_next())

    def test_sequence_number(self):
        self.assertEqual(self.add_trade(1), 1)
        self.assertEqual(self.add_trade(2), 2)

        self.assertEqual(
            self.buffer.get_stats()["sequence_number"],
            2
        )

    # -----------------------------------------
    # POISON PILL / GRACEFUL SHUTDOWN TESTS
    # -----------------------------------------

    def test_shutdown_signal_after_pending_trades(self):
        self.add_trade(1)
        self.add_trade(2)

        self.assertTrue(self.buffer.shutdown())
        self.assertTrue(self.buffer.is_shutdown)

        self.assertEqual(
            self.buffer.read_next()["trade_id"], 1
        )
        self.assertEqual(
            self.buffer.read_next()["trade_id"], 2
        )

        self.assertIs(
            self.buffer.read_next(), POISON_PILL
        )

    def test_shutdown_prevents_new_trades(self):
        self.add_trade(1)
        self.buffer.shutdown()

        with self.assertRaises(RuntimeError):
            self.add_trade(2)

    def test_repeated_shutdown_does_not_add_duplicate(self):
        self.assertTrue(self.buffer.shutdown())
        self.assertFalse(self.buffer.shutdown())

        self.assertEqual(
            self.buffer.get_stats()["unread"], 1
        )

    def test_shutdown_waits_when_buffer_is_full(self):
        self.add_trade(1)
        self.add_trade(2)
        self.add_trade(3)

        with self.assertRaises(TimeoutError):
            self.buffer.shutdown(timeout=0.05)

        self.assertEqual(
            self.buffer.get_stats()["unread"], 3
        )
        self.assertFalse(self.buffer.is_shutdown)

        self.assertEqual(
            self.buffer.read_next()["trade_id"], 1
        )
        self.assertEqual(
            self.buffer.read_next()["trade_id"], 2
        )
        self.assertEqual(
            self.buffer.read_next()["trade_id"], 3
        )

        self.assertTrue(self.buffer.shutdown())

    def test_shutdown_does_not_overwrite_pending_trades(self):
        self.add_trade(1)
        self.add_trade(2)
        self.add_trade(3)

        self.assertEqual(
            self.buffer.read_next()["trade_id"], 1
        )

        self.assertTrue(self.buffer.shutdown())

        self.assertEqual(
            self.buffer.read_next()["trade_id"], 2
        )
        self.assertEqual(
            self.buffer.read_next()["trade_id"], 3
        )

        self.assertIs(
            self.buffer.read_next(), POISON_PILL
        )

    def test_zero_copy_api_detects_shutdown_marker(self):
        self.buffer.shutdown()

        result = self.buffer.read_next_view()

        self.assertIs(result, POISON_PILL)

        with self.assertRaises(RuntimeError):
            self.buffer.consume()

        self.assertTrue(self.buffer.is_shutdown)

    def test_shutdown_marker_is_reported_in_stats(self):
        self.assertFalse(
            self.buffer.get_stats()["is_shutdown"]
        )

        self.buffer.shutdown()

        stats = self.buffer.get_stats()

        self.assertTrue(stats["is_shutdown"])
        self.assertEqual(stats["unread"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
