import os
import tempfile
import threading
import time
import unittest

from mmap_ringbuffer import MMapRingBuffer


class TestMMapRingBufferStress(unittest.TestCase):

    PRODUCERS = 4
    CONSUMERS = 4
    ORDERS_PER_PRODUCER = 1000
    TOTAL_ORDERS = PRODUCERS * ORDERS_PER_PRODUCER

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

        self.filename = os.path.join(
            self.temp_dir.name,
            "stress_ringbuffer.dat"
        )

        self.buffer = MMapRingBuffer(
            self.filename,
            capacity=self.TOTAL_ORDERS
        )

    def tearDown(self):
        self.buffer.close()
        self.temp_dir.cleanup()

    def test_multi_threaded_read_write_stress(self):

        start_barrier = threading.Barrier(
            self.PRODUCERS + self.CONSUMERS
        )

        state_lock = threading.Lock()
        result_lock = threading.Lock()

        completed_producers = 0
        received_orders = []
        errors = []

        def producer(producer_id):

            nonlocal completed_producers

            try:
                start_barrier.wait(timeout=10)

                start_id = (
                    producer_id * self.ORDERS_PER_PRODUCER
                )

                for i in range(self.ORDERS_PER_PRODUCER):

                    order_id = start_id + i + 1

                    order = {
                        "order_id": order_id,
                        "side": "B" if order_id % 2 == 0 else "S",
                        "price": 100.0 + order_id,
                        "quantity": 10 + order_id % 100,
                        "timestamp": 1720000000000 + order_id,
                    }

                    self.buffer.push(order)

            except Exception as exc:
                with state_lock:
                    errors.append(
                        ("Producer", producer_id, repr(exc))
                    )

            finally:
                with state_lock:
                    completed_producers += 1

        def consumer(consumer_id):

            local_orders = []

            try:
                start_barrier.wait(timeout=10)

                while True:

                    order = self.buffer.read_next()

                    if order is not None:
                        local_orders.append(order)
                        continue

                    with state_lock:
                        all_producers_done = (
                            completed_producers == self.PRODUCERS
                        )

                    if (
                        all_producers_done
                        and self.buffer.unread_count == 0
                    ):
                        break

                    time.sleep(0.0001)

            except Exception as exc:
                with state_lock:
                    errors.append(
                        ("Consumer", consumer_id, repr(exc))
                    )

            finally:
                with result_lock:
                    received_orders.extend(local_orders)

        threads = []

        for producer_id in range(self.PRODUCERS):
            threads.append(
                threading.Thread(
                    target=producer,
                    args=(producer_id,),
                    name=f"Producer-{producer_id}"
                )
            )

        for consumer_id in range(self.CONSUMERS):
            threads.append(
                threading.Thread(
                    target=consumer,
                    args=(consumer_id,),
                    name=f"Consumer-{consumer_id}"
                )
            )

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=60)

        alive_threads = [
            thread.name for thread in threads
            if thread.is_alive()
        ]

        self.assertEqual(
            alive_threads,
            [],
            f"Threads did not finish: {alive_threads}"
        )

        self.assertEqual(
            errors,
            [],
            f"Thread execution errors: {errors}"
        )

        received_ids = [
            order["order_id"]
            for order in received_orders
        ]

        expected_ids = set(
            range(1, self.TOTAL_ORDERS + 1)
        )

        actual_ids = set(received_ids)

        self.assertEqual(
            len(received_ids),
            self.TOTAL_ORDERS,
            "Some orders were lost or duplicated"
        )

        self.assertEqual(
            len(actual_ids),
            self.TOTAL_ORDERS,
            "Duplicate order IDs detected"
        )

        self.assertEqual(
            actual_ids,
            expected_ids,
            "Missing or unexpected order IDs detected"
        )

        for order in received_orders:

            order_id = order["order_id"]

            self.assertEqual(
                order["side"],
                "B" if order_id % 2 == 0 else "S"
            )

            self.assertAlmostEqual(
                order["price"],
                100.0 + order_id
            )

            self.assertEqual(
                order["quantity"],
                10 + order_id % 100
            )

            self.assertEqual(
                order["timestamp"],
                1720000000000 + order_id
            )

        self.assertEqual(
            self.buffer.unread_count,
            0
        )

        self.assertEqual(
            self.buffer.sequence_number,
            self.TOTAL_ORDERS * 2,
            "Unexpected ring buffer sequence number"
        )

        print(
            f"\nStress test passed: "
            f"{self.PRODUCERS} producers, "
            f"{self.CONSUMERS} consumers, "
            f"{self.TOTAL_ORDERS} orders"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
