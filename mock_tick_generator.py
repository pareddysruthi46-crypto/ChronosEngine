
import asyncio
import random
import time
import argparse

SYMBOLS = ["AAPL", "MSFT", "GOOGL"]


async def generate_mock_ticks(count=10, rate=100_000):
    """Generate mock financial ticks with a configurable target rate."""

    if count < 0:
        raise ValueError("count must be >= 0")

    if rate <= 0:
        raise ValueError("rate must be > 0")

    interval = 1.0 / rate
    next_tick_time = time.perf_counter()
    generated = 0

    while generated < count:
        tick = {
            "symbol": random.choice(SYMBOLS),
            "price": round(random.uniform(100, 250), 2),
            "quantity": random.randint(1, 1000),
            "timestamp": time.time_ns()
        }

        yield tick
        generated += 1

        next_tick_time += interval
        remaining = next_tick_time - time.perf_counter()

        if remaining > 0:
            await asyncio.sleep(remaining)
        else:
            # Behind schedule: continue without adding extra delay.
            await asyncio.sleep(0)


async def main():
    parser = argparse.ArgumentParser(
        description="Configurable asynchronous financial tick generator"
    )
    parser.add_argument(
        "--count", type=int, default=100_000,
        help="Number of ticks to generate"
    )
    parser.add_argument(
        "--rate", type=int, default=100_000,
        help="Target ticks per second"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Skip printing every tick and show only throughput"
    )

    args = parser.parse_args()

    print(f"Target rate: {args.rate:,} ticks/sec")
    print(f"Ticks to generate: {args.count:,}")

    start = time.perf_counter()

    async for tick in generate_mock_ticks(args.count, args.rate):
        if not args.quiet:
            print(tick)

    elapsed = time.perf_counter() - start
    actual_rate = args.count / elapsed if elapsed > 0 else 0

    print(f"\nGenerated: {args.count:,} ticks")
    print(f"Elapsed: {elapsed:.4f} seconds")
    print(f"Actual throughput: {actual_rate:,.0f} ticks/sec")


if __name__ == "__main__":
    asyncio.run(main())
