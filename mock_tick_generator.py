
import asyncio
import random
import time
import argparse
import struct

SYMBOLS = ["AAPL", "MSFT", "GOOGL"]

# Fixed binary layout:
# symbol: 8 bytes
# price: 8 bytes (double)
# quantity: 4 bytes (unsigned int)
# timestamp: 8 bytes (unsigned long long)
TICK_STRUCT = struct.Struct("<8sdIQ")
TICK_SIZE = TICK_STRUCT.size


def pack_tick(tick):
    """Convert a tick dictionary into a fixed-size binary payload."""
    symbol = tick["symbol"].encode("ascii")

    if len(symbol) > 8:
        raise ValueError("Symbol must be at most 8 ASCII bytes")

    return TICK_STRUCT.pack(
        symbol,
        float(tick["price"]),
        int(tick["quantity"]),
        int(tick["timestamp"])
    )


def unpack_tick(payload):
    """Decode a binary tick payload for validation."""
    if len(payload) != TICK_SIZE:
        raise ValueError(f"Payload must be exactly {TICK_SIZE} bytes")

    symbol, price, quantity, timestamp = TICK_STRUCT.unpack(payload)

    return {
        "symbol": symbol.rstrip(b"\x00").decode("ascii"),
        "price": price,
        "quantity": quantity,
        "timestamp": timestamp
    }


async def generate_mock_ticks(count=10, rate=100_000):
    """Generate simulated ticks as fixed-size binary payloads."""

    if count < 0:
        raise ValueError("count must be >= 0")

    if rate <= 0:
        raise ValueError("rate must be > 0")

    interval = 1.0 / rate
    next_tick_time = time.perf_counter()

    for _ in range(count):
        tick = {
            "symbol": random.choice(SYMBOLS),
            "price": round(random.uniform(100, 250), 2),
            "quantity": random.randint(1, 1000),
            "timestamp": time.time_ns()
        }

        payload = pack_tick(tick)
        yield payload

        next_tick_time += interval
        remaining = next_tick_time - time.perf_counter()

        if remaining > 0:
            await asyncio.sleep(remaining)
        else:
            await asyncio.sleep(0)


async def main():
    parser = argparse.ArgumentParser(
        description="Generate simulated binary financial ticks"
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
        help="Print only throughput statistics"
    )

    args = parser.parse_args()

    if args.count < 0:
        parser.error("--count must be >= 0")

    if args.rate <= 0:
        parser.error("--rate must be > 0")

    print(f"Target rate: {args.rate:,} ticks/sec")
    print(f"Ticks to generate: {args.count:,}")
    print(f"Payload size: {TICK_SIZE} bytes")

    start = time.perf_counter()
    generated = 0

    async for payload in generate_mock_ticks(args.count, args.rate):
        generated += 1

        if not args.quiet:
            print(payload.hex())

    elapsed = time.perf_counter() - start
    actual_rate = generated / elapsed if elapsed > 0 else 0

    print(f"\nGenerated: {generated:,} ticks")
    print(f"Elapsed: {elapsed:.4f} seconds")
    print(f"Actual throughput: {actual_rate:,.0f} ticks/sec")


if __name__ == "__main__":
    asyncio.run(main())