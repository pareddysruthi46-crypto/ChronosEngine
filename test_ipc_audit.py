
import os
import pickle
import tempfile
import time
import unittest
from unittest.mock import patch

from mmap_ringbuffer import MMapRingBuffer
from order_schema import pack_order

TOTAL_ORDERS = 1_000_000


def make_order(order_id):
    return {
        "order_id": order_id,
        "side": "B" if order_id % 2 else "S",
        "price": 100.0 + (order_id % 100),
        "quantity": 10,
        "timestamp": 1720000000000 + order_id,
    }


class TestIPCAudit(unittest.TestCase):

    def test_zero_pickle_calls_and_one_million_orders(self):

        with tempfile.TemporaryDirectory(
            prefix="chronos_ipc_audit_"
        ) as folder:

            filename = os.path.join(folder, "audit.dat")

            buffer = MMapRingBuffer(
                filename,
                capacity=TOTAL_ORDERS
            )

            pickle_calls = {
                "dumps": 0,
                "loads": 0
            }

            serialization_time = 0.0
            original_pack = pack_order

            def audited_pack(*args, **kwargs):
                nonlocal serialization_time

                start = time.perf_counter()
                result = original_pack(*args, **kwargs)

                serialization_time += (
                    time.perf_counter() - start
                )

                return result

            try:
                # Monitor pickle calls during ring-buffer operations.
                with patch.object(
                    pickle,
                    "dumps",
                    side_effect=lambda *args, **kwargs: (
                        pickle_calls.__setitem__(
                            "dumps",
                            pickle_calls["dumps"] + 1
                        ),
                        None
                    )[1]
                ), patch.object(
                    pickle,
                    "loads",
                    side_effect=lambda *args, **kwargs: (
                        pickle_calls.__setitem__(
                            "loads",
                            pickle_calls["loads"] + 1
                        ),
                        None
                    )[1]
                ):

                    with patch(
                        "mmap_ringbuffer.pack_order",
                        side_effect=audited_pack
                    ):

                        # Write one million orders.
                        start = time.perf_counter()

                        for order_id in range(
                            1, TOTAL_ORDERS + 1
                        ):
                            buffer.push(make_order(order_id))

                        write_time = (
                            time.perf_counter() - start
                        )

                        # Read all orders.
                        start = time.perf_counter()

                        orders = buffer.read_all()

                        read_time = (
                            time.perf_counter() - start
                        )

                # Validate order count.
                self.assertEqual(
                    len(orders),
                    TOTAL_ORDERS
                )

                # Validate every order.
                for index, order in enumerate(
                    orders, start=1
                ):
                    self.assertEqual(
                        order,
                        make_order(index)
                    )

                # Validate zero pickle calls.
                self.assertEqual(
                    pickle_calls["dumps"], 0
                )

                self.assertEqual(
                    pickle_calls["loads"], 0
                )

                # Validate sequence number.
                self.assertEqual(
                    buffer.sequence_number,
                    TOTAL_ORDERS
                )

                print("\n=== IPC Audit Results ===")
                print(
                    f"Orders validated: {len(orders):,}"
                )
                print("Missing orders: 0")
                print("Duplicate orders: 0")

                print(
                    f"Pickle dumps calls: "
                    f"{pickle_calls['dumps']}"
                )

                print(
                    f"Pickle loads calls: "
                    f"{pickle_calls['loads']}"
                )

                print(
                    f"Binary serialization time: "
                    f"{serialization_time:.6f} seconds"
                )

                print(
                    f"Writer time: {write_time:.2f} seconds"
                )

                print(
                    f"Reader time: {read_time:.2f} seconds"
                )

                print(
                    "PASS: Zero pickle calls "
                    "in ring-buffer operations"
                )

            finally:
                buffer.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
