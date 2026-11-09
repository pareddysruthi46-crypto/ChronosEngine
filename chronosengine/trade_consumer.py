
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
    """Validate a trade before adding it to the persistence queue."""

    if not isinstance(trade, dict):
        raise TypeError("Trade must be a dictionary")

    missing = REQUIRED_TRADE_FIELDS.difference(trade)

    if missing:
        raise ValueError(
            f"Trade is missing fields: {sorted(missing)}"
        )

    # Verify that the trade can be serialized.
    json.dumps(trade)


def _persist_batch(database_path, batch):
    """Persist one batch, retrying temporary database failures."""

    for attempt in range(MAX_BATCH_RETRIES):
        try:
            insert_trades_batch(database_path, batch)
            return

        except Exception:
            if attempt == MAX_BATCH_RETRIES - 1:
                raise

            time.sleep(0.5 * (attempt + 1))


def _trade_worker(trade_queue, database_path, batch_size):
    """
    Background process that persists trades in SQLite batches.

    The STOP marker is processed only after previously queued trades.
    """

    initialize_database(database_path)

    while True:
        try:
            item = trade_queue.get(timeout=0.2)

        except queue.Empty:
            continue

        if item is STOP:
            break

        batch = [item]
        stopping = False

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

        if stopping:
            break

    # The STOP marker is placed after all submissions. All preceding
    # items have now been processed, so no extra queue drain is needed.


class MatchedTradeConsumer:
    """
    Background process for asynchronous SQLite trade persistence.

    submit() validates and queues a trade.
    stop() sends the shutdown marker and waits for persistence to finish.
    """

    def __init__(
        self,
        database_path="trade_ledger.db",
        batch_size=100,
    ):
        if batch_size <= 0:
            raise ValueError(
                "batch_size must be greater than zero"
            )

        self.database_path = database_path
        self.batch_size = batch_size

        self.context = mp.get_context("spawn")
        self.trade_queue = self.context.Queue()

        self.process = None
        self._stopped = False

    def start(self):
        if self.process is not None:
            raise RuntimeError(
                "Consumer has already been started"
            )

        if self._stopped:
            raise RuntimeError(
                "Consumer cannot be restarted after stopping"
            )

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
        """Validate and submit one trade to the persistence process."""

        if self.process is None:
            raise RuntimeError(
                "Consumer has not been started"
            )

        if not self.process.is_alive():
            raise RuntimeError(
                "Trade persistence process is not running"
            )

        _validate_trade(trade)

        self.trade_queue.put(trade)

    def submit_many(self, trades):
        """Submit multiple trades in their original order."""

        for trade in trades:
            self.submit(trade)

    def stop(self, timeout=30):
        """
        Stop the persistence process after queued trades are processed.

        Raises TimeoutError if the process does not finish.
        Raises RuntimeError if the process exits unsuccessfully.
        """

        if timeout is not None and timeout < 0:
            raise ValueError(
                "timeout cannot be negative"
            )

        if self.process is None:
            return

        if self._stopped:
            return

        process = self.process

        if process.is_alive():
            self.trade_queue.put(STOP)

            process.join(timeout)

            if process.is_alive():
                raise TimeoutError(
                    "Trade consumer did not finish flushing "
                    "pending trades"
                )

        exit_code = process.exitcode

        # Close queue resources only after the process has exited.
        self.trade_queue.close()
        self.trade_queue.join_thread()

        self._stopped = True

        if exit_code != 0:
            raise RuntimeError(
                "Trade persistence process failed "
                f"with exit code {exit_code}"
            )

        self.process = None


def publish_new_engine_trades(
    engine,
    consumer,
    last_trade_count=0,
):
    """Publish newly generated matching-engine trades."""

    trades = engine.get_trades()

    if len(trades) < last_trade_count:
        last_trade_count = 0

    new_trades = trades[last_trade_count:]

    consumer.submit_many(new_trades)

    return len(trades)
