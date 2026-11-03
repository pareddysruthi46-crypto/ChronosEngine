import json
import multiprocessing as mp
import queue
import time


STOP = None

REQUIRED_TRADE_FIELDS = {
    "buy_order_id",
    "sell_order_id",
    "price",
    "quantity",
    "timestamp",
}


def _validate_trade(trade):
    if not isinstance(trade, dict):
        raise TypeError("Trade must be a dictionary")

    missing = REQUIRED_TRADE_FIELDS.difference(trade)
    if missing:
        raise ValueError(
            f"Trade is missing fields: {sorted(missing)}"
        )

    # Ensure the trade can be serialized before it enters the queue.
    json.dumps(trade)


def _trade_worker(trade_queue, output_file, batch_size):
    """Background process: consume trades and append JSONL records."""
    with open(output_file, "a", encoding="utf-8") as file:
        running = True

        while running:
            try:
                item = trade_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is STOP:
                break

            batch = [item]

            while len(batch) < batch_size:
                try:
                    item = trade_queue.get_nowait()
                except queue.Empty:
                    break

                if item is STOP:
                    running = False
                    break

                batch.append(item)

            for trade in batch:
                file.write(json.dumps(trade) + "\n")

            file.flush()


class MatchedTradeConsumer:
    """Owns a background process that persists matched trades."""

    def __init__(
        self,
        output_file="matched_trades.jsonl",
        batch_size=100,
    ):
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        self.output_file = output_file
        self.batch_size = batch_size
        self.context = mp.get_context("spawn")
        self.trade_queue = self.context.Queue()
        self.process = None

    def start(self):
        if self.process is not None:
            raise RuntimeError("Consumer has already been started")

        self.process = self.context.Process(
            target=_trade_worker,
            args=(
                self.trade_queue,
                self.output_file,
                self.batch_size,
            ),
            name="matched-trade-consumer",
        )
        self.process.start()

    def submit(self, trade):
        if self.process is None or not self.process.is_alive():
            raise RuntimeError("Consumer is not running")

        _validate_trade(trade)
        self.trade_queue.put(trade)

    def submit_many(self, trades):
        for trade in trades:
            self.submit(trade)

    def stop(self, timeout=10):
        if self.process is None:
            return

        if self.process.is_alive():
            self.trade_queue.put(STOP)
            self.process.join(timeout)

            if self.process.is_alive():
                self.process.terminate()
                self.process.join()

        self.trade_queue.close()
        self.trade_queue.join_thread()

        exit_code = self.process.exitcode
        self.process = None
        self.trade_queue = self.context.Queue()

        if exit_code != 0:
            raise RuntimeError(
                f"Trade consumer exited with code {exit_code}"
            )


def publish_new_engine_trades(engine, consumer, last_trade_count=0):
    """
    Publish trades newly appended by MatchingEngine.get_trades().

    Returns the updated trade count. If the engine's trade list shrinks,
    its count is treated as having reset.
    """
    trades = engine.get_trades()

    if len(trades) < last_trade_count:
        last_trade_count = 0

    new_trades = trades[last_trade_count:]
    consumer.submit_many(new_trades)

    return len(trades)