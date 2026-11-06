import argparse
import tempfile
import time
from pathlib import Path

from chronosengine.trade_consumer import MatchedTradeConsumer
from chronosengine.trade_ledger import initialize_database, get_trade_count


def make_trade(number, total):
    return {
        "buy_order_id": number + 1,
        "sell_order_id": number + total + 1,
        "price": 100.0 + (number % 10000) / 100.0,
        "quantity": 1 + (number % 100),
        "timestamp": 1_700_000_000_000 + number,
    }


def run_benchmark(total_trades, batch_size, chunk_size, target_rate):
    with tempfile.TemporaryDirectory() as folder:
        database = str(Path(folder) / "benchmark_trades.db")
        initialize_database(database)

        consumer = MatchedTradeConsumer(
            database_path=database,
            batch_size=batch_size,
        )

        submitted = 0
        max_sampled_backlog = 0
        submit_seconds = 0.0

        consumer.start()
        start_time = time.perf_counter()

        try:
            while submitted < total_trades:
                current_chunk = min(
                    chunk_size,
                    total_trades - submitted,
                )

                chunk_start = time.perf_counter()

                for _ in range(current_chunk):
                    consumer.submit(make_trade(submitted, total_trades))
                    submitted += 1

                submit_seconds += time.perf_counter() - chunk_start

                # Pace submissions when a target rate is requested.
                if target_rate:
                    expected_elapsed = submitted / target_rate
                    actual_elapsed = time.perf_counter() - start_time

                    if expected_elapsed > actual_elapsed:
                        time.sleep(expected_elapsed - actual_elapsed)

                persisted = get_trade_count(database)
                pending = submitted - persisted
                max_sampled_backlog = max(
                    max_sampled_backlog,
                    pending,
                )

            submit_finished = time.perf_counter()

            deadline = time.perf_counter() + 120

            while True:
                persisted = get_trade_count(database)
                pending = submitted - persisted

                max_sampled_backlog = max(
                    max_sampled_backlog,
                    pending,
                )

                if persisted == total_trades:
                    break

                if not consumer.process.is_alive():
                    raise RuntimeError(
                        "Persistence worker exited before all trades "
                        "were saved."
                    )

                if time.perf_counter() >= deadline:
                    raise TimeoutError(
                        f"Timed out: persisted {persisted}/{total_trades}"
                    )

                time.sleep(0.05)

            drained_time = time.perf_counter()

        finally:
            consumer.stop(timeout=120)

        final_count = get_trade_count(database)

        producer_elapsed = submit_finished - start_time
        drain_seconds = drained_time - submit_finished
        end_to_end_seconds = drained_time - start_time

        producer_rate = (
            submitted / producer_elapsed if producer_elapsed > 0 else 0
        )
        persistence_rate = (
            final_count / end_to_end_seconds
            if end_to_end_seconds > 0 else 0
        )

        print("\n===== TRADE INGESTION BENCHMARK =====")
        print(f"Trades submitted       : {submitted}")
        print(f"Trades persisted       : {final_count}")
        print(f"Missing trades         : {submitted - final_count}")
        print(f"Batch size             : {batch_size}")
        print(f"Chunk size             : {chunk_size}")
        print(f"Target producer rate   : {target_rate or 'Unpaced'}")
        print(f"Producer elapsed       : {producer_elapsed:.4f} sec")
        print(f"Actual submit time     : {submit_seconds:.4f} sec")
        print(f"Queue drain time       : {drain_seconds:.4f} sec")
        print(f"End-to-end time        : {end_to_end_seconds:.4f} sec")
        print(f"Producer rate          : {producer_rate:,.0f} fills/sec")
        print(f"Persistence rate       : {persistence_rate:,.0f} fills/sec")
        print(
            f"Max sampled backlog   : {max_sampled_backlog:,} trades"
        )

        if final_count != submitted:
            raise RuntimeError("Benchmark failed: trade count mismatch.")

        print("\nRESULT: PASS - every submitted trade was persisted.")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark asynchronous SQLite trade ingestion."
    )
    parser.add_argument("--trades", type=int, default=50000)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument(
        "--target-rate",
        type=int,
        default=0,
        help="Target producer rate in fills/sec; 0 means unpaced.",
    )

    args = parser.parse_args()

    if args.trades <= 0:
        parser.error("--trades must be greater than zero")
    if args.batch_size <= 0 or args.chunk_size <= 0:
        parser.error("--batch-size and --chunk-size must be positive")
    if args.target_rate < 0:
        parser.error("--target-rate cannot be negative")

    run_benchmark(
        args.trades,
        args.batch_size,
        args.chunk_size,
        args.target_rate,
    )


if __name__ == "__main__":
    main()
