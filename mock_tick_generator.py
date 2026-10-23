
import asyncio
import random
import time

SYMBOLS = ["AAPL", "MSFT", "GOOGL"]


async def generate_mock_ticks(count=10):
    """Generate sample financial ticks asynchronously."""

    for _ in range(count):
        tick = {
            "symbol": random.choice(SYMBOLS),
            "price": round(random.uniform(100, 250), 2),
            "quantity": random.randint(1, 1000),
            "timestamp": time.time_ns()
        }

        yield tick

        # Simulate a short delay between ticks
        await asyncio.sleep(0.1)


async def main():
    print("Starting mock financial tick generator...\n")

    async for tick in generate_mock_ticks():
        print(tick)

    print("\nMock tick generation completed.")


if __name__ == "__main__":
    asyncio.run(main())
