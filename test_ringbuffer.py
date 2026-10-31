
import os
import tempfile
import unittest

from mmap_ringbuffer import MMapRingBuffer


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
        self.filename = os.path.join(self.temp_dir.name, "ringbuffer.dat")
        self.buffer = MMapRingBuffer(self.filename, capacity=3)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
