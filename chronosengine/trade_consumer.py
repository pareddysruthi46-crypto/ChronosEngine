import json
import multiprocessing as mp
import queue
import time

from chronosengine.trade_ledger import (
    initialize_database,
    insert_trades_batch,
)


STOP = None
MAX_BATCH_RETRIES = 5

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

    json.dumps(trade)


def _persist_batch(database_path, batch):
    """Retry a failed SQLite batch a limited number of times."""
    for attempt in range(MAX_BATCH_RETRIES):
        try:
            insert_trades_batch(database_path, batch)
            return
        except Exception:
            if attempt == MAX_BATCH_RETRIES - 1:
                raise

            time.sleep(0.5 * (attempt + 1))


def _trade_worker(trade_queue, database_path, batch_size):
    """Persist queued trades asynchronously in SQLite batches."""
    initialize_database(database_path)
    stopping = False

    while not stopping:
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
                stopping = True
                break

            batch.append(item)

        _persist_batch(database_path, batch)

    # Flush remaining queued trades before worker shutdown.
    while True:
        batch = []

        while len(batch) < batch_size:
            try:
                item = trade_queue.get_nowait()
            except queue.Empty:
                break

            if item is not STOP:
                batch.append(item)

        if not batch:
            break

        _persist_batch(database_path, batch)


class MatchedTradeConsumer:
    """Background process for batched SQLite trade persistence."""

    def __init__(
        self,
        database_path="trade_ledger.db",
        batch_size=100,
    ):
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        self.database_path = database_path
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
                self.database_path,
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
                raise TimeoutError(
                    "Consumer did not finish flushing pending trades"
                )

        exit_code = self.process.exitcode

        self.trade_queue.close()
        self.trade_queue.join_thread()

        self.process = None

        if exit_code != 0:
            raise RuntimeError(
                f"Trade consumer exited with code {exit_code}"
            )


def publish_new_engine_trades(engine, consumer, last_trade_count=0):
    """Publish newly generated matching-engine trades."""
    trades = engine.get_trades()

    if len(trades) < last_trade_count:
        last_trade_count = 0

    new_trades = trades[last_trade_count:]
    consumer.submit_many(new_trades)

    return len(trades)