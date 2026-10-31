
import multiprocessing
import os
import tempfile

from mmap_ringbuffer import MMapRingBuffer


def producer(filename, start, count):
    """Write orders from a separate process."""
    buffer = MMapRingBuffer(filename, capacity=1000)

    try:
        for i in range(start, start + count):
            buffer.push({
                "order_id": i,
                "side": "B",
                "price": 100.0,
                "quantity": 1,
                "timestamp": i,
            })
    finally:
        buffer.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as folder:
        filename = os.path.join(folder, "shared.dat")

        # Initialize the shared buffer only once.
        buffer = MMapRingBuffer(filename, capacity=1000)
        buffer.close()

        # Start three independent producer processes.
        processes = [
            multiprocessing.Process(
                target=producer,
                args=(filename, i * 100, 100),
            )
            for i in range(1, 4)
        ]

        for process in processes:
            process.start()

        # Wait for every process to finish.
        for process in processes:
            process.join()

        # Verify that all producer processes completed successfully.
        for process in processes:
            assert process.exitcode == 0, (
                f"Producer process {process.pid} failed "
                f"with exit code {process.exitcode}"
            )

        # Reopen the same buffer without resetting its contents.
        buffer = MMapRingBuffer(filename, capacity=1000)

        try:
            orders = buffer.read_all()
            sequence = buffer.sequence_number
            unread = buffer.unread_count

            print("Producer processes completed successfully.")
            print("Stored order count:", len(orders))
            print("Sequence number:", sequence)
            print("Unread count:", unread)

            # Each producer writes 100 orders: 3 * 100 = 300.
            assert len(orders) == 300, (
                f"Expected 300 orders, found {len(orders)}"
            )

            # Each push increments the sequence once.
            assert sequence == 300, (
                f"Expected sequence 300, found {sequence}"
            )

            assert unread == 300, (
                f"Expected 300 unread orders, found {unread}"
            )

            # Verify that no order IDs are missing or duplicated.
            order_ids = [order["order_id"] for order in orders]
            expected_ids = set(range(100, 400))

            assert len(set(order_ids)) == 300, (
                "Duplicate order IDs found"
            )
            assert set(order_ids) == expected_ids, (
                "Some order IDs are missing or unexpected"
            )

            print("Multiprocessing test PASSED.")

        finally:
            buffer.close()
