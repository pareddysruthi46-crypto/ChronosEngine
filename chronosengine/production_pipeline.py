
import asyncio
import os
import tempfile
import threading
import time

from mock_tick_generator import generate_mock_orders
from mmap_ringbuffer import MMapRingBuffer
from mmap_trade_ringbuffer import MmapTradeRingBuffer
from order_schema import ORDER_STRUCT
from shutdown_signal import POISON_PILL

from chronosengine.matching_engine import MatchingEngine
from chronosengine.trade_consumer import MatchedTradeConsumer


class ProductionPipeline:
    """
    Simulated live trading pipeline:

        Mock producer
            -> Order mmap buffer
            -> Matching engine
            -> Trade mmap buffer
            -> SQLite persistence

    The dashboard shares this pipeline's engine and buffers.
    """

    def __init__(
        self,
        count=1000,
        rate=1000,
        order_capacity=1000,
        trade_capacity=1000,
        database_path="trade_ledger.db",
        news_profile="none",
        burst_rate=None,
        burst_duration=5.0,
        news_delay=1.0,
    ):
        if count < 0:
            raise ValueError("count must be >= 0")

        if rate <= 0:
            raise ValueError("rate must be > 0")

        if order_capacity <= 0 or trade_capacity <= 0:
            raise ValueError("Buffer capacities must be positive")

        if burst_rate is not None and burst_rate <= 0:
            raise ValueError("burst_rate must be > 0")

        if burst_duration <= 0 or news_delay < 0:
            raise ValueError(
                "burst_duration must be > 0 and news_delay must be >= 0"
            )

        if news_profile not in ("none", "earnings"):
            raise ValueError(
                "news_profile must be 'none' or 'earnings'"
            )

        self.count = count
        self.rate = rate
        self.news_profile = news_profile
        self.burst_rate = burst_rate
        self.burst_duration = burst_duration
        self.news_delay = news_delay
        self.database_path = database_path

        self.engine = MatchingEngine()

        self.stop_event = threading.Event()
        self.errors = []

        self._error_lock = threading.Lock()
        self._counter_lock = threading.Lock()

        self.generated_orders = 0
        self.processed_orders = 0
        self.submitted_trades = 0

        self._temp_dir = tempfile.TemporaryDirectory(
            prefix="chronosengine_"
        )

        order_path = os.path.join(
            self._temp_dir.name,
            "orders.dat",
        )

        trade_path = os.path.join(
            self._temp_dir.name,
            "trades.dat",
        )

        self.order_buffer = MMapRingBuffer(
            order_path,
            capacity=order_capacity,
        )

        self.trade_buffer = MmapTradeRingBuffer(
            trade_path,
            capacity=trade_capacity,
        )

        self.persistence = MatchedTradeConsumer(
            database_path=database_path,
            batch_size=100,
        )

        self.producer_thread = None
        self.order_thread = None
        self.trade_thread = None

        self.started = False
        self._resources_closed = False

    @property
    def finished_orders(self):
        """Return the number of successfully processed orders."""
        return self.processed_orders

    @property
    def finished_trades(self):
        """Return the number of trades submitted for persistence."""
        return self.submitted_trades

    def _record_error(self, exc):
        with self._error_lock:
            self.errors.append(exc)

        self.stop_event.set()

    def _increment_counter(self, counter_name, amount=1):
        with self._counter_lock:
            setattr(
                self,
                counter_name,
                getattr(self, counter_name) + amount,
            )

    async def _produce_orders(self):
        """Generate orders and apply backpressure to the order buffer."""

        try:
            async for order in generate_mock_orders(
                count=self.count,
                rate=self.rate,
                news_profile=self.news_profile,
                burst_rate=self.burst_rate,
                burst_duration=self.burst_duration,
                news_delay=self.news_delay,
            ):
                if self.stop_event.is_set():
                    break

                # Wait while the order buffer is full.
                while (
                    self.order_buffer.get_stats()["unread"]
                    >= self.order_buffer.capacity
                ):
                    if self.stop_event.is_set():
                        break

                    await asyncio.sleep(0.001)

                if self.stop_event.is_set():
                    break

                timestamp = time.time_ns()

                payload = ORDER_STRUCT.pack(
                    order["order_id"],
                    order["side"].encode("ascii"),
                    order["price"],
                    order["quantity"],
                    timestamp,
                )

                self.order_buffer.push_packed(
                    payload,
                    flush=False,
                )

                self._increment_counter("generated_orders")

        finally:
            try:
                self.order_buffer.flush()
            except Exception as exc:
                self._record_error(exc)

            try:
                self.order_buffer.shutdown(timeout=30.0)
            except Exception as exc:
                self._record_error(exc)

    def _producer_worker(self):
        try:
            asyncio.run(self._produce_orders())
        except Exception as exc:
            self._record_error(exc)

    def _order_worker(self):
        """
        Read orders, match them, and publish newly created trades.
        """

        last_trade_count = 0
        next_trade_id = 1

        try:
            while True:
                order = self.order_buffer.read_next()

                if order is None:
                    time.sleep(0.001)
                    continue

                if order is POISON_PILL:
                    break

                self.engine.submit_order(
                    order["order_id"],
                    order["side"],
                    order["price"],
                    order["quantity"],
                    order["timestamp"],
                )

                self._increment_counter("processed_orders")

                new_trades = self.engine.get_trades_since(last_trade_count)
                last_trade_count += len(new_trades)

                for trade in new_trades:
                    while True:
                        try:
                            self.trade_buffer.push_trade(
                                next_trade_id,
                                trade["buy_order_id"],
                                trade["sell_order_id"],
                                trade["price"],
                                trade["quantity"],
                                trade["timestamp"],
                            )
                            break

                        except BufferError:
                            if (
                                self.trade_thread is not None
                                and not self.trade_thread.is_alive()
                            ):
                                raise RuntimeError(
                                    "Trade consumer exited while "
                                    "the trade buffer was full"
                                )

                            time.sleep(0.001)

                    next_trade_id += 1

        except Exception as exc:
            self._record_error(exc)

        finally:
            try:
                self.trade_buffer.shutdown(timeout=30.0)
            except Exception as exc:
                self._record_error(exc)

    def _trade_worker(self):
        """
        Drain the trade buffer and submit records to SQLite persistence.
        """

        try:
            while True:
                trade = self.trade_buffer.read_next()

                if trade is None:
                    time.sleep(0.001)
                    continue

                if trade is POISON_PILL:
                    break

                self.persistence.submit(trade)

                self._increment_counter("submitted_trades")

        except Exception as exc:
            self._record_error(exc)

        finally:
            try:
                self.persistence.stop(timeout=30)
            except Exception as exc:
                self._record_error(exc)

    def start(self):
        """Start persistence and all pipeline workers."""

        if self.started:
            raise RuntimeError(
                "Pipeline has already been started"
            )

        if self._resources_closed:
            raise RuntimeError(
                "Pipeline resources have already been closed"
            )

        self.persistence.start()

        self.trade_thread = threading.Thread(
            target=self._trade_worker,
            name="chronos-trade-consumer",
            daemon=True,
        )

        self.order_thread = threading.Thread(
            target=self._order_worker,
            name="chronos-order-consumer",
            daemon=True,
        )

        self.producer_thread = threading.Thread(
            target=self._producer_worker,
            name="chronos-order-producer",
            daemon=True,
        )

        self.trade_thread.start()
        self.order_thread.start()
        self.producer_thread.start()

        self.started = True

        return self

    def stop(self):
        """
        Stop order generation and drain downstream pipeline stages.

        Already-published orders and trades are allowed to finish.
        """

        if not self.started:
            return

        self.stop_event.set()

        self.producer_thread.join(timeout=35)

        if self.producer_thread.is_alive():
            raise TimeoutError(
                "Order producer did not stop"
            )

        self.order_thread.join(timeout=35)

        if self.order_thread.is_alive():
            raise TimeoutError(
                "Order consumer did not stop"
            )

        self.trade_thread.join(timeout=35)

        if self.trade_thread.is_alive():
            raise TimeoutError(
                "Trade consumer did not stop"
            )

        # All worker threads have exited. Resources can now be closed.
        self.order_buffer.close()
        self.trade_buffer.close()

        self._temp_dir.cleanup()

        self.started = False
        self._resources_closed = True

        if self.errors:
            details = "; ".join(
                repr(error) for error in self.errors
            )

            raise RuntimeError(
                "Production pipeline failed: " + details
            )

        if self.generated_orders != self.processed_orders:
            raise RuntimeError(
                "Order count mismatch: "
                f"generated={self.generated_orders}, "
                f"processed={self.processed_orders}"
            )

    def get_status(self):
        """Return a snapshot of pipeline counters and buffer metrics."""

        with self._counter_lock:
            generated = self.generated_orders
            processed = self.processed_orders
            submitted = self.submitted_trades

        with self._error_lock:
            error_count = len(self.errors)

        return {
            "generated_orders": generated,
            "processed_orders": processed,
            "submitted_trades": submitted,
            "order_buffer": self.order_buffer.get_stats(),
            "trade_buffer": self.trade_buffer.get_stats(),
            "errors": error_count,
        }
