import multiprocessing as mp
import os
import statistics
import tempfile
import time
import math

from mmap_trade_ringbuffer import MmapTradeRingBuffer
from trade_schema import unpack_trade
from shutdown_signal import POISON_PILL


MESSAGES = 5000
WARMUP = 500
CAPACITY = 64


def consumer_worker(path, total, ready, ack, started):
    """Consume mmap-backed trade views in a separate process."""
    buffer = None

    try:
        buffer = MmapTradeRingBuffer(path, CAPACITY)
        started.set()

        for expected_id in range(1, total + 1):
            if not ready.wait(timeout=30):
                raise TimeoutError("Timed out waiting for producer")

            ready.clear()

            view = buffer.read_next_view()

            if view is None or view is POISON_PILL:
                raise RuntimeError("Expected trade payload was missing")

            try:
                trade = unpack_trade(view)

                if trade["trade_id"] != expected_id:
                    raise ValueError(
                        f"Expected trade {expected_id}, "
                        f"received {trade['trade_id']}"
                    )

                if trade["quantity"] != 10:
                    raise ValueError("Trade quantity mismatch")

            finally:
                view.release()

            buffer.consume()
            ack.set()

    finally:
        if buffer is not None:
            buffer.close()


def percentile(values, percent):
    ordered = sorted(values)
    index = max(0, math.ceil(percent * len(ordered)) - 1)
    return ordered[index]


def benchmark_zero_copy_roundtrip():
    total = WARMUP + MESSAGES
    context = mp.get_context("spawn")

    ready = context.Event()
    ack = context.Event()
    started = context.Event()

    fd, path = tempfile.mkstemp(
        prefix="chronos_zero_copy_",
        suffix=".dat"
    )
    os.close(fd)
    os.unlink(path)

    producer_buffer = None
    process = None
    latencies = []
    completed = 0

    try:
        producer_buffer = MmapTradeRingBuffer(path, CAPACITY)

        process = context.Process(
            target=consumer_worker,
            args=(path, total, ready, ack, started)
        )
        process.start()

        if not started.wait(timeout=30):
            raise TimeoutError("Consumer process failed to initialize")

        benchmark_start = None

        for i in range(total):
            trade_id = i + 1

            payload_timestamp = time.perf_counter_ns()

            if i == WARMUP:
                benchmark_start = time.perf_counter_ns()

            start = time.perf_counter_ns()

            producer_buffer.push_trade(
                trade_id=trade_id,
                buy_order_id=100000 + trade_id,
                sell_order_id=200000 + trade_id,
                price=125.50,
                quantity=10,
                timestamp=payload_timestamp
            )

            ready.set()

            if not ack.wait(timeout=30):
                raise TimeoutError(
                    f"Consumer acknowledgement missing for {trade_id}"
                )

            ack.clear()

            if i >= WARMUP:
                latencies.append(time.perf_counter_ns() - start)
                completed += 1

        benchmark_elapsed = (
            time.perf_counter_ns() - benchmark_start
        )

        process.join(timeout=30)

        if process.is_alive():
            process.terminate()
            process.join()
            raise TimeoutError("Consumer process did not exit")

        if process.exitcode != 0:
            raise RuntimeError(
                f"Consumer exited with code {process.exitcode}"
            )

        if completed != MESSAGES:
            raise RuntimeError("Benchmark message count mismatch")

        print("\n=== Zero-Copy IPC Round-Trip Benchmark ===")
        print("Transport: Shared memory-mapped trade ring buffer")
        print("Consumer: Separate process")
        print("Read API: mmap-backed memoryview")
        print(f"Record size: 40 bytes")
        print(f"Warmup messages: {WARMUP:,}")
        print(f"Measured messages: {completed:,}")
        print(f"Lost messages: {MESSAGES - completed}")

        print(
            f"Throughput: "
            f"{completed / (benchmark_elapsed / 1e9):,.0f} msg/sec"
        )

        print(
            f"Mean round-trip latency: "
            f"{statistics.fmean(latencies) / 1000:.2f} us"
        )

        print(
            f"P50 latency: {percentile(latencies, 0.50) / 1000:.2f} us"
        )
        print(
            f"P95 latency: {percentile(latencies, 0.95) / 1000:.2f} us"
        )
        print(
            f"P99 latency: {percentile(latencies, 0.99) / 1000:.2f} us"
        )
        print(
            f"Max latency: {max(latencies) / 1000:.2f} us"
        )

        print(
            f"Total benchmark time: "
            f"{benchmark_elapsed / 1e9:.4f} sec"
        )

        print("Payload validation: PASSED")
        print("Consumer process: PASSED")

    finally:
        if process is not None and process.is_alive():
            process.terminate()
            process.join()

        if producer_buffer is not None:
            producer_buffer.close()

        if os.path.exists(path):
            os.unlink(path)

        lock_path = path + ".lock"
        if os.path.exists(lock_path):
            os.unlink(lock_path)


if __name__ == "__main__":
    mp.freeze_support()
    benchmark_zero_copy_roundtrip()

