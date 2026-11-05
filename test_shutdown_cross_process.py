
import multiprocessing
import os
import tempfile
import time
import unittest

from mmap_ringbuffer import (
    MMapRingBuffer,
    POISON_PILL as ORDER_POISON_PILL
)

from mmap_trade_ringbuffer import (
    MmapTradeRingBuffer,
    POISON_PILL as TRADE_POISON_PILL
)


def order_consumer(filename, result_queue):
    try:
        received = []

        with MMapRingBuffer(filename, capacity=3) as buffer:
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                item = buffer.read_next()

                if item is ORDER_POISON_PILL:
                    result_queue.put(("ok", received))
                    return

                if item is not None:
                    received.append(item["order_id"])

                time.sleep(0.01)

        result_queue.put(
            ("error", "Order shutdown marker not received")
        )

    except Exception as exc:
        result_queue.put(("error", repr(exc)))


def trade_consumer(filename, result_queue):
    try:
        received = []

        with MmapTradeRingBuffer(filename, capacity=3) as buffer:
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                item = buffer.read_next()

                if item is TRADE_POISON_PILL:
                    result_queue.put(("ok", received))
                    return

                if item is not None:
                    received.append(item["trade_id"])

                time.sleep(0.01)

        result_queue.put(
            ("error", "Trade shutdown marker not received")
        )

    except Exception as exc:
        result_queue.put(("error", repr(exc)))


class TestCrossProcessShutdown(unittest.TestCase):

    def run_consumer_process(self, target, filename):
        context = multiprocessing.get_context("spawn")
        result_queue = context.Queue()

        process = context.Process(
            target=target,
            args=(filename, result_queue)
        )

        process.start()
        process.join(timeout=10)

        if process.is_alive():
            process.terminate()
            process.join()
            result_queue.close()
            result_queue.join_thread()
            self.fail("Consumer process did not terminate")

        self.assertEqual(process.exitcode, 0)

        try:
            status, result = result_queue.get(timeout=3)
        finally:
            result_queue.close()
            result_queue.join_thread()

        self.assertEqual(status, "ok", result)

        return result

    def test_order_shutdown_across_processes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, "orders.dat")

            buffer = MMapRingBuffer(filename, capacity=3)

            try:
                buffer.push({
                    "order_id": 1,
                    "side": "B",
                    "price": 100.0,
                    "quantity": 10,
                    "timestamp": 1720000000001
                })

                buffer.push({
                    "order_id": 2,
                    "side": "S",
                    "price": 101.0,
                    "quantity": 5,
                    "timestamp": 1720000000002
                })

                self.assertTrue(buffer.shutdown())

            finally:
                buffer.close()

            received = self.run_consumer_process(
                order_consumer,
                filename
            )

            self.assertEqual(received, [1, 2])

    def test_trade_shutdown_across_processes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, "trades.dat")

            buffer = MmapTradeRingBuffer(filename, capacity=3)

            try:
                buffer.push_trade(
                    1, 101, 201, 125.50, 5, 1720000000001
                )

                buffer.push_trade(
                    2, 102, 202, 126.50, 3, 1720000000002
                )

                self.assertTrue(buffer.shutdown())

            finally:
                buffer.close()

            received = self.run_consumer_process(
                trade_consumer,
                filename
            )

            self.assertEqual(received, [1, 2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
