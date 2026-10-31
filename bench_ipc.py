

import mmap
import multiprocessing as mp
import os
import pickle
import statistics
import tempfile
import time

from order_schema import ORDER_STRUCT, pack_order, unpack_order


ITERATIONS = 20_000
WARMUP = 1_000
IPC_MESSAGES = 2_000
RAW_STRUCT = ORDER_STRUCT


def make_order(order_id):
    return {
        "order_id": order_id,
        "side": "B",
        "price": 125.50,
        "quantity": 10,
        "timestamp": 1720000000000 + order_id,
    }


def print_latency_results(name, latencies, count, record_size=None):
    elapsed = sum(latencies) / 1e9
    ordered = sorted(latencies)

    print(f"\n=== {name} ===")
    print(f"Messages: {count:,}")
    print(f"Round-trip throughput: {count / elapsed:,.0f} msg/sec")
    print(
        f"Mean round-trip latency: "
        f"{statistics.mean(latencies) / 1000:.2f} us"
    )
    print(
        f"P95 round-trip latency: "
        f"{ordered[min(int(count * 0.95), count - 1)] / 1000:.2f} us"
    )

    if record_size is not None:
        print(f"Record size: {record_size} bytes")


def benchmark_serialization():
    """Compare pickle and raw struct serialization throughput."""
    order = make_order(1)

    cases = [
        (
            "pickle",
            lambda: pickle.dumps(
                order, protocol=pickle.HIGHEST_PROTOCOL
            ),
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

        total_bytes = 0
        start = time.perf_counter()

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
    """Child process receives pickled orders and acknowledges them."""
    try:
        for _ in range(count):
            payload = conn.recv_bytes()
            order = pickle.loads(payload)

            # Consume the decoded record so the receive path is exercised.
            if order["order_id"] < 0:
                raise ValueError("Invalid order ID")

            conn.send_bytes(b"1")
    finally:
        conn.close()


def benchmark_pipe():
    """Measure cross-process Pipe round-trip latency using pickle."""
    count = IPC_MESSAGES
    parent, child = mp.Pipe(duplex=True)
    process = mp.Process(target=pipe_worker, args=(child, count))
    process.start()
    child.close()

    latencies = []

    try:
        for i in range(count):
            payload = pickle.dumps(
                make_order(i + 1),
                protocol=pickle.HIGHEST_PROTOCOL,
            )

            start = time.perf_counter_ns()
            parent.send_bytes(payload)
            parent.recv_bytes()
            latencies.append(time.perf_counter_ns() - start)
    finally:
        parent.close()
        process.join(timeout=15)

        if process.is_alive():
            process.terminate()
            process.join()

    if process.exitcode != 0:
        raise RuntimeError(
            f"Pipe worker exited with code {process.exitcode}"
        )

    print_latency_results(
        "Cross-process Pipe (pickle + acknowledgement)",
        latencies,
        count,
    )


def benchmark_mmap():
    """Measure same-process mmap raw-record write/read latency."""
    count = ITERATIONS
    record_size = RAW_STRUCT.size
    file_size = record_size * count

    fd, path = tempfile.mkstemp(
        prefix="chronos_bench_",
        suffix=".dat",
    )
    latencies = []

    try:
        os.ftruncate(fd, file_size)

        with mmap.mmap(fd, file_size) as mm:
            for i in range(count):
                payload = pack_order(
                    i + 1,
                    "B",
                    125.50,
                    10,
                    1720000000000 + i,
                )

                offset = i * record_size
                start = time.perf_counter_ns()

                mm[offset:offset + record_size] = payload
                record = mm[offset:offset + record_size]
                unpack_order(record)

                latencies.append(time.perf_counter_ns() - start)

        print_latency_results(
            "Same-process mmap (write + read)",
            latencies,
            count,
            record_size,
        )
    finally:
        os.close(fd)
        os.unlink(path)


def mmap_consumer(path, count, ready, ack):
    """Child process reads records from the shared mmap."""
    record_size = ORDER_STRUCT.size

    with open(path, "r+b") as file:
        with mmap.mmap(file.fileno(), record_size) as mm:
            for _ in range(count):
                if not ready.wait(timeout=15):
                    raise TimeoutError("Timed out waiting for mmap record")

                record = mm[:record_size]
                order = unpack_order(record)

                if order["order_id"] < 1:
                    raise ValueError("Invalid order ID in mmap")

                ready.clear()
                ack.set()


def benchmark_cross_process_mmap():
    """Measure shared mmap round-trip latency across two processes."""
    count = IPC_MESSAGES
    record_size = ORDER_STRUCT.size

    fd, path = tempfile.mkstemp(
        prefix="chronos_shared_",
        suffix=".dat",
    )
    os.ftruncate(fd, record_size)
    os.close(fd)

    ready = mp.Event()
    ack = mp.Event()
    process = mp.Process(
        target=mmap_consumer,
        args=(path, count, ready, ack),
    )
    latencies = []

    try:
        process.start()

        with open(path, "r+b") as file:
            with mmap.mmap(file.fileno(), record_size) as mm:
                for i in range(count):
                    payload = pack_order(
                        i + 1,
                        "B",
                        125.50,
                        10,
                        1720000000000 + i,
                    )

                    start = time.perf_counter_ns()
                    mm[:record_size] = payload
                    ready.set()

                    if not ack.wait(timeout=15):
                        raise TimeoutError(
                            "Timed out waiting for mmap acknowledgement"
                        )

                    latencies.append(time.perf_counter_ns() - start)
                    ack.clear()

        process.join(timeout=15)

        if process.is_alive():
            process.terminate()
            process.join()
            raise TimeoutError("mmap consumer did not exit")

        if process.exitcode != 0:
            raise RuntimeError(
                f"mmap consumer exited with code {process.exitcode}"
            )

        print_latency_results(
            "Cross-process shared mmap (raw struct + acknowledgement)",
            latencies,
            count,
            record_size,
        )
    finally:
        if process.is_alive():
            process.terminate()
            process.join()

        os.unlink(path)


if __name__ == "__main__":
    mp.freeze_support()

    print(f"Serialization iterations: {ITERATIONS:,}")
    print(f"IPC messages: {IPC_MESSAGES:,}")

    benchmark_serialization()
    benchmark_pipe()
    benchmark_mmap()
    benchmark_cross_process_mmap()
