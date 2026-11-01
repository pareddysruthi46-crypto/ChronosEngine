
import os
import time
from datetime import datetime, timezone

from chronosengine.matching_engine import MatchingEngine


SELL_COUNT = 5_000
BUY_COUNT = 5_000
TOTAL_ORDERS = SELL_COUNT + BUY_COUNT
RUNS = 2


def build_workload():
    """Create the same deterministic workload for every run."""
    orders = []

    # First add resting sell orders at five price levels.
    for i in range(SELL_COUNT):
        orders.append({
            "order_id": i + 1,
            "side": "S",
            "price": float(100 + (i % 5)),
            "quantity": 1 + (i % 9),
            "timestamp": i + 1,
        })

    # Then submit aggressive buys that consume resting sells.
    for i in range(BUY_COUNT):
        orders.append({
            "order_id": SELL_COUNT + i + 1,
            "side": "B",
            "price": 110.0,
            "quantity": 1 + ((i * 7) % 11),
            "timestamp": SELL_COUNT + i + 1,
        })

    return orders


def calculate_expected_result(orders):
    """
    Independent Python reference model.

    Uses lowest sell price first and timestamp priority
    within each price level.
    """
    resting_sells = []
    expected_trades = []
    expected_buys = []

    for order in orders:
        if order["side"] == "S":
            resting_sells.append(order.copy())
            continue

        remaining = order["quantity"]

        while remaining > 0 and resting_sells:
            # Price priority, then timestamp priority.
            resting_sells.sort(
                key=lambda item: (
                    item["price"],
                    item["timestamp"],
                )
            )

            maker = resting_sells[0]

            if order["price"] < maker["price"]:
                break

            trade_quantity = min(
                remaining,
                maker["quantity"],
            )

            expected_trades.append({
                "buy_order_id": order["order_id"],
                "sell_order_id": maker["order_id"],
                "price": maker["price"],
                "quantity": trade_quantity,
                "timestamp": order["timestamp"],
            })

            remaining -= trade_quantity
            maker["quantity"] -= trade_quantity

            if maker["quantity"] == 0:
                resting_sells.pop(0)

        if remaining > 0:
            expected_buys.append({
                "order_id": order["order_id"],
                "side": "B",
                "price": order["price"],
                "quantity": remaining,
                "timestamp": order["timestamp"],
            })

    return expected_trades, {
        "buys": expected_buys,
        "sells": resting_sells,
    }


def run_engine(orders):
    engine = MatchingEngine()

    start = time.perf_counter()

    for order in orders:
        engine.submit_order(
            order["order_id"],
            order["side"],
            order["price"],
            order["quantity"],
            order["timestamp"],
        )

    elapsed = time.perf_counter() - start

    return (
        engine.get_trades(),
        engine.get_order_book(),
        elapsed,
    )


def main():
    orders = build_workload()

    expected_trades, expected_book = (
        calculate_expected_result(orders)
    )

    results = []
    timings = []

    for run_number in range(1, RUNS + 1):
        trades, order_book, elapsed = run_engine(orders)

        assert trades == expected_trades, (
            f"Run {run_number}: trade mismatch. "
            f"Expected {len(expected_trades)}, "
            f"received {len(trades)}."
        )

        assert order_book == expected_book, (
            f"Run {run_number}: remaining order book mismatch."
        )

        results.append((trades, order_book))
        timings.append(elapsed)

    # Verify repeated executions are identical.
    assert results[0] == results[1], (
        "Determinism check failed."
    )

    total_traded_quantity = sum(
        trade["quantity"] for trade in expected_trades
    )

    report = [
        "CHRONOSENGINE MATCH ACCURACY STRESS REPORT",
        "=" * 48,
        f"Generated at (UTC): {datetime.now(timezone.utc).isoformat()}",
        "",
        "WORKLOAD",
        f"Sell orders: {SELL_COUNT:,}",
        f"Buy orders: {BUY_COUNT:,}",
        f"Total orders per run: {TOTAL_ORDERS:,}",
        f"Validation runs: {RUNS}",
        "",
        "MATCHING ACCURACY",
        f"Expected trades: {len(expected_trades):,}",
        f"Actual trades per run: {len(results[0][0]):,}",
        f"Traded quantity: {total_traded_quantity:,}",
        "Trade field mismatches: 0",
        "Remaining order-book mismatches: 0",
        "Missing trades: 0",
        "Unexpected trades: 0",
        "Deterministic repeated runs: PASS",
        "",
        "EXECUTION PERFORMANCE",
    ]

    for index, elapsed in enumerate(timings, start=1):
        throughput = TOTAL_ORDERS / elapsed
        report.append(
            f"Run {index}: {elapsed:.6f} seconds, "
            f"{throughput:,.0f} orders/second"
        )

    average_time = sum(timings) / len(timings)
    average_throughput = TOTAL_ORDERS / average_time

    report.extend([
        f"Average execution time: {average_time:.6f} seconds",
        f"Average throughput: {average_throughput:,.0f} orders/second",
        "",
        "FINAL RESULT: PASS",
        "All actual trades and remaining orders matched "
        "the independent reference model.",
    ])

    output = "\n".join(report)

    os.makedirs("reports", exist_ok=True)

    report_path = os.path.join(
        "reports",
        "match_accuracy_stress_report.txt",
    )

    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write(output + "\n")

    print(output)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
