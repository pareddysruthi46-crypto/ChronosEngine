
import mmap
import multiprocessing as mp
import os
import pickle
import statistics
import struct
import tempfile
import time

from order_schema import pack_order, unpack_order, ORDER_STRUCT


ITERATIONS = 20_000
WARMUP = 1_000

# Fixed-size raw binary record for mmap benchmark.
RAW_STRUCT = ORDER_STRUCT


def make_order(order_id):
    return {
        "order_id": order_id,
        "side": "B",
        "price": 125.50,
        "quantity": 10,
        "timestamp": 1720000000000 + order_id,
    }


def benchmark_serialization():
    """Compare pickle serialization against raw struct serialization."""
    order = make_order(1)

    cases = [
        (
            "pickle",
            lambda: pickle.dumps(order, protocol=pickle.HIGHEST_PROTOCOL),
        ),
        (
            "raw struct",
            lambda: pack_order(
                order["order_id"],
                order["side"],
                order["price"],
                order["quantity"],
                order["timestamp"],
            ),
        ),
    ]

    print("\n=== Serialization benchmark ===")
    for name, operation in cases:
        for _ in range(WARMUP):
            operation()

        start = time.perf_counter()
        total_bytes = 0

        for _ in range(ITERATIONS):
            total_bytes += len(operation())

        elapsed = time.perf_counter() - start
        print(
            f"{name:12} | "
            f"{ITERATIONS / elapsed:,.0f} ops/sec | "
            f"{elapsed * 1e6 / ITERATIONS:.2f} us/op | "
            f"{total_bytes / ITERATIONS:.0f} bytes/op"
        )


def pipe_worker(conn, count):
    """Child process: receive serialized records and acknowledge each one."""
    try:
        for _ in range(count):
            payload = conn.recv_bytes()
            order = pickle.loads(payload)
            conn.send_bytes(b"1")
    finally:
        conn.close()


def benchmark_pipe():
    """Measure round-trip latency through a real multiprocessing pipe."""
    count = 2_000
    parent, child = mp.Pipe(duplex=True)
    process = mp.Process(target=pipe_worker, args=(child, count))
    process.start()
    child.close()

    latencies = []
    order = make_order(1)

    try:
        # One send/ack exchange per message.
        for i in range(count):
            payload = pickle.dumps(
                make_order(i), protocol=pickle.HIGHEST_PROTOCOL
            )
            start = time.perf_counter_ns()
            parent.send_bytes(payload)
            parent.recv_bytes()
            latencies.append(time.perf_counter_ns() - start)
    finally:
        parent.close()
        process.join()

    if process.exitcode != 0:
        raise RuntimeError(f"Pipe worker exited with {process.exitcode}")

    total_seconds = sum(latencies) / 1e9
    print("\n=== Cross-process pipe benchmark ===")
    print(f"Messages: {count:,}")
    print(f"Round-trip throughput: {count / total_seconds:,.0f} msg/sec")
    print(f"Mean round-trip latency: {statistics.mean(latencies) / 1000:.2f} us")
    print(f"P95 round-trip latency: {sorted(latencies)[int(count * 0.95)] / 1000:.2f} us")


def benchmark_mmap():
    """Measure local mmap write/read latency using the project's record layout."""
    count = ITERATIONS
    record_size = RAW_STRUCT.size
    header_size = 0
    file_size = record_size * count

    fd, path = tempfile.mkstemp(prefix="chronos_bench_", suffix=".dat")
    latencies = []

    try:
        os.ftruncate(fd, file_size)

        with mmap.mmap(fd, file_size) as mm:
            for i in range(count):
                payload = pack_order(
                    i + 1, "B", 125.50, 10, 1720000000000 + i
                )

                start = time.perf_counter_ns()
                offset = i * record_size
                mm[offset:offset + record_size] = payload
                record = mm[offset:offset + record_size]
                unpack_order(record)
                latencies.append(time.perf_counter_ns() - start)

        elapsed = sum(latencies) / 1e9
        print("\n=== mmap raw-struct benchmark (same process) ===")
        print(f"Messages: {count:,}")
        print(f"Write+read throughput: {count / elapsed:,.0f} msg/sec")
        print(f"Mean write+read latency: {statistics.mean(latencies) / 1000:.2f} us")
        print(f"P95 write+read latency: {sorted(latencies)[int(count * 0.95)] / 1000:.2f} us")
        print(f"Record size: {record_size} bytes")
    finally:
        os.close(fd)
        os.unlink(path)


if __name__ == "__main__":
    mp.freeze_support()
    print(f"Iterations: {ITERATIONS:,}")
    benchmark_serialization()
    benchmark_pipe()
    benchmark_mmap()
