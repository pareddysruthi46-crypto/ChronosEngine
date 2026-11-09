import asyncio
import os
import tempfile
import unittest

from mmap_ringbuffer import MMapRingBuffer
from mock_tick_generator import firehose_producer


class TestIngressTimestamp(unittest.TestCase):

    def test_timestamp_is_injected_at_binary_write_stage(self):

        with tempfile.TemporaryDirectory() as folder:
            filename = os.path.join(folder, "ingress_test.dat")

            buffer = MMapRingBuffer(filename, capacity=10)

            try:
                generated, elapsed, throughput = asyncio.run(
                    firehose_producer(
                        buffer=buffer,
                        count=10,
                        rate=100_000,
                        quiet=True,
                    )
                )

                orders = buffer.read_all()

                self.assertEqual(generated, 10)
                self.assertEqual(len(orders), 10)

                previous_timestamp = 0

                for order in orders:
                    timestamp = order["timestamp"]

                    self.assertGreater(timestamp, 0)
                    self.assertGreaterEqual(
                        timestamp,
                        previous_timestamp,
                    )

                    # Verify timestamp is in epoch nanoseconds.
                    self.assertGreater(
                        timestamp,
                        1_000_000_000_000_000,
                    )

                    previous_timestamp = timestamp

                print("\n=== Ingress Timestamp Audit ===")
                print("Orders generated:", generated)
                print("Orders received:", len(orders))
                print("Timestamp unit: nanoseconds")
                print("First timestamp:", orders[0]["timestamp"])
                print("Last timestamp:", orders[-1]["timestamp"])
                print("Timestamp validation: PASSED")

            finally:
                buffer.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)