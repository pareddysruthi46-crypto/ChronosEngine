
import asyncio
import random
import time
import argparse

from mmap_ringbuffer import MMapRingBuffer


async def generate_mock_orders(count=10, rate=100_000):
    """Generate simulated orders asynchronously."""

    if count < 0:
        raise ValueError("count must be >= 0")

    if rate <= 0:
        raise ValueError("rate must be > 0")

    interval = 1.0 / rate
    next_order_time = time.perf_counter()

    for i in range(count):
        order = {
            "order_id": i + 1,
            "side": random.choice(["B", "S"]),
            "price": round(random.uniform(100, 250), 2),
            "quantity": random.randint(1, 1000),
            "timestamp": time.time_ns()
        }

        yield order

        next_order_time += interval
        remaining = next_order_time - time.perf_counter()

        if remaining > 0:
            await asyncio.sleep(remaining)
        else:
            await asyncio.sleep(0)


async def firehose_producer(buffer, count, rate, quiet=False):
    """Generate orders and write directly into the mmap buffer."""

    start = time.perf_counter()
    generated = 0

    async for order in generate_mock_orders(count, rate):
        buffer.push(order)
        generated += 1

        if not quiet:
            print("Written:", order)

    elapsed = time.perf_counter() - start
    throughput = generated / elapsed if elapsed > 0 else 0

    return generated, elapsed, throughput


async def main():
    parser = argparse.ArgumentParser(
        description="Async order producer for the mmap ring buffer"
    )

    parser.add_argument(
        "--count",
        type=int,
        default=100_000,
        help="Number of orders to generate"
    )

    parser.add_argument(
        "--rate",
        type=int,
        default=100_000,
        help="Target orders per second"
    )

    parser.add_argument(
        "--capacity",
        type=int,
        default=100,
        help="Maximum number of orders stored in the buffer"
    )

    parser.add_argument(
        "--buffer",
        default="orders_buffer.dat",
        help="Mmap buffer file path"
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress individual order output"
    )

    args = parser.parse_args()

    if args.count < 0:
        parser.error("--count must be >= 0")

    if args.rate <= 0:
        parser.error("--rate must be > 0")

    if args.capacity <= 0:
        parser.error("--capacity must be > 0")

    buffer = MMapRingBuffer(
        args.buffer,
        capacity=args.capacity
    )

    try:
        print("Target rate:", f"{args.rate:,}", "orders/sec")
        print("Orders to generate:", f"{args.count:,}")
        print("Buffer capacity:", args.capacity)

        generated, elapsed, throughput = await firehose_producer(
            buffer,
            args.count,
            args.rate,
            args.quiet
        )

        stored_orders = buffer.read_all()

        print("\n--- Producer Results ---")
        print("Generated:", generated)
        print(f"Elapsed: {elapsed:.4f} seconds")
        print(f"Throughput: {throughput:,.0f} orders/sec")
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
