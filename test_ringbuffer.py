
import os
import tempfile
import unittest

from mmap_ringbuffer import MMapRingBuffer, POISON_PILL


def make_order(order_id):
    return {
        "order_id": order_id,
        "side": "B",
        "price": 100.0 + order_id,
        "quantity": 10,
        "timestamp": 1720000000000 + order_id,
    }


class TestRingBufferBoundaryAndWraparound(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.filename = os.path.join(
            self.temp_dir.name, "ringbuffer.dat"
        )
        self.buffer = MMapRingBuffer(
            self.filename, capacity=3
        )

    def tearDown(self):
        self.buffer.close()
        self.temp_dir.cleanup()

    def test_empty_buffer_returns_no_order(self):
        self.assertIsNone(self.buffer.read_next())
        self.assertEqual(self.buffer.unread_count, 0)

    def test_exact_capacity_boundary(self):
        for order_id in (1, 2, 3):
            self.buffer.push(make_order(order_id))

        self.assertEqual(
            [order["order_id"] for order in self.buffer.read_all()],
            [1, 2, 3],
        )
        self.assertEqual(self.buffer.unread_count, 3)

    def test_write_index_wraps_to_start(self):
        for order_id in (1, 2, 3, 4):
            self.buffer.push(make_order(order_id))

        self.assertEqual(
            [order["order_id"] for order in self.buffer.read_all()],
            [2, 3, 4],
        )

    def test_capacity_overflow_keeps_newest_orders(self):
        for order_id in (1, 2, 3, 4, 5):
            self.buffer.push(make_order(order_id))

        self.assertEqual(
            [order["order_id"] for order in self.buffer.read_all()],
            [3, 4, 5],
        )
        self.assertEqual(self.buffer.unread_count, 3)

    def test_wraparound_after_consuming_orders(self):
        for order_id in (1, 2, 3):
            self.buffer.push(make_order(order_id))

        self.assertEqual(self.buffer.read_next()["order_id"], 1)
        self.assertEqual(self.buffer.read_next()["order_id"], 2)

        self.buffer.push(make_order(4))
        self.buffer.push(make_order(5))

        self.assertEqual(
            [order["order_id"] for order in self.buffer.read_all()],
            [3, 4, 5],
        )

        self.assertEqual(
            [self.buffer.read_next()["order_id"] for _ in range(3)],
            [3, 4, 5],
        )

        self.assertIsNone(self.buffer.read_next())

    def test_zero_capacity_is_rejected(self):
        with self.assertRaises(ValueError):
            MMapRingBuffer(self.filename, capacity=0)

    def test_close_is_idempotent(self):
        self.buffer.close()
        self.buffer.close()

        self.assertIsNone(self.buffer.mm)
        self.assertIsNone(self.buffer.file)
        self.assertIsNone(self.buffer.lock_file)

    def test_context_manager_closes_resources(self):
        filename = os.path.join(
            self.temp_dir.name, "context_buffer.dat"
        )

        with MMapRingBuffer(filename, capacity=3) as buffer:
            buffer.push(make_order(10))

            self.assertEqual(
                buffer.read_all()[0]["order_id"], 10
            )

        self.assertIsNone(buffer.mm)
        self.assertIsNone(buffer.file)
        self.assertIsNone(buffer.lock_file)

    def test_close_preserves_buffer_file(self):
        self.buffer.push(make_order(20))
        self.buffer.close()

        self.assertTrue(os.path.exists(self.filename))
        self.assertGreater(os.path.getsize(self.filename), 0)

    # -----------------------------------------
    # POISON PILL / GRACEFUL SHUTDOWN TESTS
    # -----------------------------------------

    def test_shutdown_signal_after_pending_orders(self):
        self.buffer.push(make_order(1))
        self.buffer.push(make_order(2))

        self.assertTrue(self.buffer.shutdown())

        self.assertEqual(
            self.buffer.read_next()["order_id"], 1
        )
        self.assertEqual(
            self.buffer.read_next()["order_id"], 2
        )

        self.assertIs(
            self.buffer.read_next(), POISON_PILL
        )

    def test_shutdown_prevents_new_orders(self):
        self.buffer.push(make_order(1))
        self.buffer.shutdown()

        with self.assertRaises(RuntimeError):
            self.buffer.push(make_order(2))

    def test_repeated_shutdown_does_not_add_duplicate(self):
        self.assertTrue(self.buffer.shutdown())
        self.assertFalse(self.buffer.shutdown())

        self.assertEqual(self.buffer.unread_count, 1)

    def test_shutdown_waits_when_buffer_is_full(self):
        for order_id in (1, 2, 3):
            self.buffer.push(make_order(order_id))

        with self.assertRaises(TimeoutError):
            self.buffer.shutdown(timeout=0.05)

        self.assertEqual(self.buffer.unread_count, 3)
        self.assertFalse(self.buffer.is_shutdown)

        self.assertEqual(
            [
                self.buffer.read_next()["order_id"]
                for _ in range(3)
            ],
            [1, 2, 3],
        )

    def test_shutdown_does_not_overwrite_pending_orders(self):
        for order_id in (1, 2, 3):
            self.buffer.push(make_order(order_id))

        # Consume one order to make room for the shutdown marker.
        self.assertEqual(
            self.buffer.read_next()["order_id"], 1
        )

        self.assertTrue(self.buffer.shutdown())

        self.assertEqual(
            self.buffer.read_next()["order_id"], 2
        )
        self.assertEqual(
            self.buffer.read_next()["order_id"], 3
        )

        self.assertIs(
            self.buffer.read_next(), POISON_PILL
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
