
import asyncio
import random
import time
import argparse

from mmap_ringbuffer import MMapRingBuffer


async def generate_mock_orders(
    count=10,
    rate=100_000,
    news_profile="none",
    burst_rate=None,
    burst_duration=5.0,
    news_delay=1.0,
):
    """Generate orders with an optional earnings-news volume burst."""

    if count < 0:
        raise ValueError("count must be >= 0")
    if rate <= 0:
        raise ValueError("rate must be > 0")
    if news_profile not in ("none", "earnings"):
        raise ValueError("news_profile must be 'none' or 'earnings'")
    if burst_duration <= 0:
        raise ValueError("burst_duration must be > 0")
    if news_delay < 0:
        raise ValueError("news_delay must be >= 0")

    if burst_rate is None:
        burst_rate = rate * 5

    if burst_rate <= 0:
        raise ValueError("burst_rate must be > 0")

    start_time = time.perf_counter()
    next_order_time = start_time
    news_announced = False

    for i in range(count):
        now = time.perf_counter()
        elapsed = now - start_time

        in_burst = (
            news_profile == "earnings"
            and news_delay <= elapsed < news_delay + burst_duration
        )

        if (
            news_profile == "earnings"
            and not news_announced
            and elapsed >= news_delay
        ):
            print(
                f"\n[NEWS] Earnings announcement! "
                f"Burst profile active for {burst_duration:.2f}s."
            )
            news_announced = True

        current_rate = burst_rate if in_burst else rate

        order = {
            "order_id": i + 1,
            "side": random.choice(["B", "S"]),
            "price": round(random.uniform(100, 250), 2),
            "quantity": random.randint(1, 1000),
            "timestamp": time.time_ns(),
        }

        yield order

        next_order_time += 1.0 / current_rate
        remaining = next_order_time - time.perf_counter()

        if remaining > 0:
            await asyncio.sleep(remaining)
        else:
            # Yield control to other asynchronous tasks.
            await asyncio.sleep(0)


async def firehose_producer(
    buffer,
    count,
    rate,
    quiet=False,
    news_profile="none",
    burst_rate=None,
    burst_duration=5.0,
    news_delay=1.0,
):
    """Generate orders asynchronously and write them to the mmap buffer."""

    start = time.perf_counter()
    generated = 0

    async for order in generate_mock_orders(
        count=count,
        rate=rate,
        news_profile=news_profile,
        burst_rate=burst_rate,
        burst_duration=burst_duration,
        news_delay=news_delay,
    ):
        buffer.push(order)
        generated += 1

        if not quiet:
            print("Written:", order)

    elapsed = time.perf_counter() - start
    throughput = generated / elapsed if elapsed > 0 else 0

    return generated, elapsed, throughput


async def main():
    parser = argparse.ArgumentParser(
        description="Async order producer with optional earnings-news burst"
    )

    parser.add_argument(
        "--count",
        type=int,
        default=100_000,
        help="Number of orders to generate",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=100_000,
        help="Normal target orders per second",
    )
    parser.add_argument(
        "--capacity",
        type=int,
        default=100,
        help="Maximum number of orders stored in the buffer",
    )
    parser.add_argument(
        "--buffer",
        default="orders_buffer.dat",
        help="Mmap buffer file path",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress individual order output",
    )
    parser.add_argument(
        "--news-profile",
        choices=("none", "earnings"),
        default="none",
        help="Select normal generation or simulated earnings-news burst",
    )
    parser.add_argument(
        "--burst-rate",
        type=int,
        default=None,
        help="Orders per second during the burst (default: 5x normal rate)",
    )
    parser.add_argument(
        "--burst-duration",
        type=float,
        default=5.0,
        help="Duration of the earnings-news burst in seconds",
    )
    parser.add_argument(
        "--news-delay",
        type=float,
        default=1.0,
        help="Seconds after generation starts before earnings news",
    )

    args = parser.parse_args()

    if args.count < 0:
        parser.error("--count must be >= 0")
    if args.rate <= 0:
        parser.error("--rate must be > 0")
    if args.capacity <= 0:
        parser.error("--capacity must be > 0")
    if args.burst_rate is not None and args.burst_rate <= 0:
        parser.error("--burst-rate must be > 0")
    if args.burst_duration <= 0:
        parser.error("--burst-duration must be > 0")
    if args.news_delay < 0:
        parser.error("--news-delay must be >= 0")

    burst_rate = (
        args.burst_rate
        if args.burst_rate is not None
        else args.rate * 5
    )

    buffer = MMapRingBuffer(args.buffer, capacity=args.capacity)

    try:
        print("Normal target rate:", f"{args.rate:,}", "orders/sec")
        print("Orders to generate:", f"{args.count:,}")
        print("Buffer capacity:", args.capacity)
        print("News profile:", args.news_profile)

        if args.news_profile == "earnings":
            print("Burst target rate:", f"{burst_rate:,}", "orders/sec")
            print("Burst duration:", args.burst_duration, "seconds")
            print("News delay:", args.news_delay, "seconds")

        generated, elapsed, throughput = await firehose_producer(
            buffer=buffer,
            count=args.count,
            rate=args.rate,
            quiet=args.quiet,
            news_profile=args.news_profile,
            burst_rate=burst_rate,
            burst_duration=args.burst_duration,
            news_delay=args.news_delay,
        )

        stored_orders = buffer.read_all()

        print("\n--- Producer Results ---")
        print("Generated:", generated)
        print(f"Elapsed: {elapsed:.4f} seconds")
        print(f"Average throughput: {throughput:,.0f} orders/sec")
        print("Stored in buffer:", len(stored_orders))
        print("Unread orders:", buffer.unread_count)

        if stored_orders:
            print("First stored order:", stored_orders[0])
            print("Last stored order:", stored_orders[-1])

        if generated == 0:
            print("No orders generated.")
        elif len(stored_orders) == min(generated, args.capacity):
            print("Buffer verification: PASSED")
        else:
            print("Buffer verification: FAILED")

    finally:
        buffer.close()


if __name__ == "__main__":
    asyncio.run(main())
