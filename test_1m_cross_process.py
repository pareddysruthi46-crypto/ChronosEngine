import multiprocessing as mp
import os
import tempfile
import time

from mmap_ringbuffer import MMapRingBuffer

TOTAL_ORDERS = 1_000_000
CAPACITY = TOTAL_ORDERS


def make_order(order_id):
    return {
        "order_id": order_id,
        "side": "B" if order_id % 2 else "S",
        "price": 100.0 + (order_id % 100),
        "quantity": 10,
        "timestamp": 1720000000000 + order_id,
    }


def writer_process(filename, count, result_queue):
    """Write orders from a separate process."""
    buffer = MMapRingBuffer(filename, capacity=CAPACITY)

    try:
        start = time.perf_counter()

        for order_id in range(1, count + 1):
            buffer.push(make_order(order_id))

        elapsed = time.perf_counter() - start

        result_queue.put({
            "written": count,
            "sequence": buffer.sequence_number,
            "elapsed": elapsed,
        })
    finally:
        buffer.close()


def reader_process(filename, count, result_queue):
    """Read and validate orders from a separate process."""
    buffer = MMapRingBuffer(filename, capacity=CAPACITY)

    try:
        start = time.perf_counter()

        orders = buffer.read_all()

        if len(orders) != count:
            raise AssertionError(
                f"Expected {count} orders, received {len(orders)}"
            )

        for expected_id, order in enumerate(orders, start=1):
            if order["order_id"] != expected_id:
                raise AssertionError(
                    f"Order mismatch at position {expected_id}: "
                    f"received {order['order_id']}"
                )

            expected = make_order(expected_id)

            if order != expected:
                raise AssertionError(
                    f"Data mismatch for order {expected_id}: {order}"
                )

        elapsed = time.perf_counter() - start

        result_queue.put({
            "received": len(orders),
            "unread": buffer.unread_count,
            "elapsed": elapsed,
        })
    finally:
        buffer.close()


def main():
    mp.freeze_support()

    with tempfile.TemporaryDirectory(
        prefix="chronos_1m_test_"
    ) as folder:

        filename = os.path.join(folder, "orders_1m.dat")

        # Initialize the shared ring buffer before starting processes.
        buffer = MMapRingBuffer(filename, capacity=CAPACITY)
        buffer.close()

        writer_results = mp.Queue()
        reader_results = mp.Queue()

        writer = mp.Process(
            target=writer_process,
            args=(filename, TOTAL_ORDERS, writer_results),
            name="OrderWriter",
        )

        reader = mp.Process(
            target=reader_process,
            args=(filename, TOTAL_ORDERS, reader_results),
            name="OrderReader",
        )

        print("Starting 1M order cross-process validation...")
        print(f"Total orders: {TOTAL_ORDERS:,}")
        print(f"Record size: 29 bytes")
        print(f"Buffer capacity: {CAPACITY:,}")

        overall_start = time.perf_counter()

        writer.start()
        writer.join()

        if writer.exitcode != 0:
            raise RuntimeError(
                f"Writer process failed: {writer.exitcode}"
            )

        write_result = writer_results.get(timeout=30)

        print("\nWriter process completed.")
        print("Orders written:", f"{write_result['written']:,}")
        print("Writer sequence:", f"{write_result['sequence']:,}")

        reader.start()
        reader.join()

        if reader.exitcode != 0:
            raise RuntimeError(
                f"Reader process failed: {reader.exitcode}"
            )

        read_result = reader_results.get(timeout=30)

        total_elapsed = time.perf_counter() - overall_start

        print("\nReader process completed.")
        print("Orders received:", f"{read_result['received']:,}")
        print("Unread records:", f"{read_result['unread']:,}")
        print("Data integrity: PASSED")
        print("Missing orders: 0")
        print("Duplicate orders: 0")

        print("\n=== Performance Summary ===")
        print(f"Writer time: {write_result['elapsed']:.2f} seconds")
        print(f"Reader time: {read_result['elapsed']:.2f} seconds")
        print(f"Total time: {total_elapsed:.2f} seconds")

        print(
            "Writer throughput:",
            f"{TOTAL_ORDERS / write_result['elapsed']:,.0f} orders/sec",
        )

        print(
            "Reader throughput:",
            f"{TOTAL_ORDERS / read_result['elapsed']:,.0f} orders/sec",
        )

        print("\nPASS: 1M cross-process order transmission validated!")


if __name__ == "__main__":
    main()
