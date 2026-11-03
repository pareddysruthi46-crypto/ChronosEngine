import time
from mmap_ringbuffer import MMapRingBuffer
from order_schema import ORDER_STRUCT

TOTAL_ORDERS = 500_000
TARGET_RATE = 100_000
BUFFER_FILE = "async_stress_test.dat"


def run_stress_test():
    buffer = MMapRingBuffer(
        BUFFER_FILE,
        capacity=TOTAL_ORDERS
    )

    payload = bytearray(ORDER_STRUCT.size)

    try:
        print("Starting async firehose buffer stress test")
        print(f"Target throughput: {TARGET_RATE:,} orders/sec")
        print(f"Total orders: {TOTAL_ORDERS:,}")
        print(f"Buffer capacity: {TOTAL_ORDERS:,}")

        start = time.perf_counter()

        for order_id in range(1, TOTAL_ORDERS + 1):
            ORDER_STRUCT.pack_into(
                payload,
                0,
                order_id,
                b"B" if order_id % 2 else b"S",
                100.0 + (order_id % 100),
                10,
                time.time_ns(),
                b"L"
            )

            # Write without flushing every individual record.
            buffer._write_record(payload)

        buffer.mm.flush()
        elapsed = time.perf_counter() - start

        received = buffer.read_all()
        throughput = len(received) / elapsed if elapsed else 0

        ids = [order["order_id"] for order in received]
        unique_ids = set(ids)

        missing = TOTAL_ORDERS - len(unique_ids)
        duplicates = len(ids) - len(unique_ids)

        print("\n--- Stress Test Results ---")
        print(f"Generated: {TOTAL_ORDERS:,}")
        print(f"Received: {len(received):,}")
        print(f"Elapsed: {elapsed:.3f} seconds")
        print(f"Throughput: {throughput:,.0f} orders/sec")
        print(f"Missing orders: {missing}")
        print(f"Duplicate orders: {duplicates}")

        passed = (
            len(received) == TOTAL_ORDERS
            and missing == 0
            and duplicates == 0
            and throughput >= TARGET_RATE
        )

        if passed:
            print("\nPASS: 100K orders/sec target achieved with zero drops!")
        else:
            print("\nFAIL: Stress-test requirements not achieved.")

        if ids and (ids[0] != 1 or ids[-1] != TOTAL_ORDERS):
            print("WARNING: First/last order ID mismatch.")

        return passed

    finally:
        buffer.close()


if __name__ == "__main__":
    run_stress_test()
