import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from math import ceil

from chronosengine.matching_engine import MatchingEngine


WARMUP_ORDERS = 1000
MEASURED_ORDERS = 10000
RUNS = 5
TARGET_NS = 50_000


def percentile(values, percent):
    ordered = sorted(values)
    rank = max(1, ceil(percent * len(ordered)))
    return ordered[rank - 1]


def run_warmup():
    engine = MatchingEngine()
    engine.submit_order(1, "S", 100.0, WARMUP_ORDERS, 1)

    for i in range(WARMUP_ORDERS):
        result = engine.submit_order(
            i + 2, "B", 101.0, 1, i + 2
        )
        if result["filled_quantity"] != 1:
            raise RuntimeError("Warm-up matching failed")


def run_benchmark(run_number):
    engine = MatchingEngine()

    # One resting sell order provides liquidity for every measured buy.
    engine.submit_order(
        1, "S", 100.0, MEASURED_ORDERS, 1
    )

    latencies = []

    for i in range(MEASURED_ORDERS):
        start = time.perf_counter_ns()

        result = engine.submit_order(
            i + 2, "B", 101.0, 1, i + 2
        )

        elapsed = time.perf_counter_ns() - start
        latencies.append(elapsed)

        if result["filled_quantity"] != 1:
            raise RuntimeError(
                f"Matching failed in run {run_number}, order {i + 1}"
            )

    trades = engine.get_trades()

    if len(trades) != MEASURED_ORDERS:
        raise RuntimeError(
            f"Expected {MEASURED_ORDERS} trades, got {len(trades)}"
        )

    return latencies, len(trades)


def format_us(ns):
    return f"{ns / 1000:.3f} µs"


def main():
    print("Warming up matching engine...")
    run_warmup()

    all_latencies = []
    run_results = []

    print("\nStarting benchmark...")

    for run_number in range(1, RUNS + 1):
        latencies, trade_count = run_benchmark(run_number)
        all_latencies.extend(latencies)

        run_results.append({
            "run": run_number,
            "latencies": latencies,
            "trades": trade_count,
        })

        print(
            f"Run {run_number}: "
            f"average={format_us(statistics.mean(latencies))}, "
            f"p99={format_us(percentile(latencies, 0.99))}, "
            f"trades={trade_count}"
        )

    average = statistics.mean(all_latencies)
    median = statistics.median(all_latencies)
    p90 = percentile(all_latencies, 0.90)
    p99 = percentile(all_latencies, 0.99)
    maximum = max(all_latencies)
    minimum = min(all_latencies)

    under_target = sum(
        1 for value in all_latencies if value < TARGET_NS
    )
    under_percentage = under_target / len(all_latencies) * 100

    total_trades = sum(result["trades"] for result in run_results)

    passed = p99 < TARGET_NS

    lines = [
        "CHRONOSENGINE MATCHING LATENCY BENCHMARK",
        "=" * 48,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Python version: {sys.version}",
        f"Platform: {platform.platform()}",
        "",
        "WORKLOAD",
        f"Warm-up orders: {WARMUP_ORDERS}",
        f"Measured orders per run: {MEASURED_ORDERS}",
        f"Measured runs: {RUNS}",
        f"Total measured matching operations: {len(all_latencies)}",
        f"Total verified trades: {total_trades}",
        "",
        "END-TO-END submit_order() LATENCY",
        f"Average: {format_us(average)}",
        f"Median (P50): {format_us(median)}",
        f"P90: {format_us(p90)}",
        f"P99: {format_us(p99)}",
        f"Minimum: {format_us(minimum)}",
        f"Maximum: {format_us(maximum)}",
        f"Operations below 50 us: {under_target}",
        f"Percentage below 50 us: {under_percentage:.3f}%",
        "",
        "PER-RUN RESULTS",
    ]

    for result in run_results:
        values = result["latencies"]
        lines.append(
            f"Run {result['run']}: "
            f"average={format_us(statistics.mean(values))}, "
            f"P50={format_us(percentile(values, 0.50))}, "
            f"P99={format_us(percentile(values, 0.99))}, "
            f"max={format_us(max(values))}, "
            f"trades={result['trades']}"
        )

    lines.extend([
        "",
        "TARGET: P99 latency below 50 microseconds",
        f"FINAL RESULT: {'PASS' if passed else 'NOT PASS'}",
        "",
        "Note: Latency measures the Python-visible submit_order() call",
        "including the actual matching operation and trade recording.",
        "It does not measure the complete mmap producer-to-consumer pipeline.",
    ])

    os.makedirs("reports", exist_ok=True)

    report_path = os.path.join(
        "reports", "sub_50_microsecond_benchmark.txt"
    )

    with open(report_path, "w", encoding="utf-8") as report:
        report.write("\n".join(lines) + "\n")

    print("\n" + "\n".join(lines))
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
