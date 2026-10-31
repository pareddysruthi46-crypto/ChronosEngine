import curses
import threading
import time
from collections import deque

from chronosengine.matching_engine import MatchingEngine


# Dashboard configuration
DEPTH_LEVELS = 5
REFRESH_INTERVAL_MS = 250
OPS_WINDOW_SECONDS = 1.0
TRADE_BUFFER_SIZE = 8
LATENCY_SAMPLE_SIZE = 1000
ENGINE_POLL_INTERVAL_SECONDS = 0.05


def calculate_latency_stats(samples):
    """Calculate engine snapshot polling latency in microseconds."""
    if not samples:
        return None

    values = sorted(samples)
    count = len(values)

    def percentile(p):
        index = max(0, min(count - 1, int((p / 100) * count)))
        return values[index]

    return {
        "min": values[0],
        "avg": sum(values) / count,
        "max": values[-1],
        "p50": percentile(50),
        "p95": percentile(95),
        "p99": percentile(99),
    }


def get_observed_order_ids(order_book, trades):
    """Collect order IDs currently visible in the book or trade history."""
    order_ids = set()

    for side in ("buys", "sells"):
        for order in order_book.get(side, []):
            order_id = order.get("order_id")
            if order_id is not None:
                order_ids.add(order_id)

    for trade in trades:
        for field in ("buy_order_id", "sell_order_id"):
            order_id = trade.get(field)
            if order_id is not None:
                order_ids.add(order_id)

    return order_ids


def aggregate_depth(orders):
    """Aggregate total quantity and order count at each price level."""
    levels = {}
    for order in orders:
        price = float(order["price"])
        if price not in levels:
            levels[price] = {"quantity": 0, "orders": 0}
        levels[price]["quantity"] += int(order["quantity"])
        levels[price]["orders"] += 1
    return levels


class EngineSnapshotWorker:
    """Poll the engine in the background and publish immutable UI snapshots."""

    def __init__(self, engine):
        self.engine = engine
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._snapshot = {
            "order_book": {"buys": [], "sells": []},
            "recent_trades": [],
            "ops": 0,
            "latency_stats": None,
            "error": None,
        }
        self._thread = threading.Thread(
            target=self._run,
            name="ChronosEngineSnapshotWorker",
            daemon=True,
        )
        self._recent_trades = deque(maxlen=TRADE_BUFFER_SIZE)
        self._recent_order_times = deque()
        self._latency_samples = deque(maxlen=LATENCY_SAMPLE_SIZE)
        self._seen_order_ids = set()
        self._last_trade_count = 0

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def get_latest_snapshot(self):
        """Return a defensive copy so the UI cannot mutate worker state."""
        with self._lock:
            book = self._snapshot["order_book"]
            return {
                "order_book": {
                    "buys": [dict(order) for order in book["buys"]],
                    "sells": [dict(order) for order in book["sells"]],
                },
                "recent_trades": [
                    dict(trade) for trade in self._snapshot["recent_trades"]
                ],
                "ops": self._snapshot["ops"],
                "latency_stats": (
                    dict(self._snapshot["latency_stats"])
                    if self._snapshot["latency_stats"] else None
                ),
                "error": self._snapshot["error"],
            }

    def _run(self):
        while not self._stop_event.is_set():
            try:
                start_ns = time.perf_counter_ns()
                engine_data = self.engine.get_snapshot()
                end_ns = time.perf_counter_ns()

                latency_us = (end_ns - start_ns) / 1000.0
                order_book = engine_data["order_book"]
                trades = engine_data["trades"]

                self._latency_samples.append(latency_us)
                latency_stats = calculate_latency_stats(self._latency_samples)

                # Detect a reset of the engine's trade history.
                if len(trades) < self._last_trade_count:
                    self._last_trade_count = 0
                    self._recent_trades.clear()

                new_trades = trades[self._last_trade_count:]
                for trade in new_trades:
                    self._recent_trades.append(dict(trade))
                self._last_trade_count = len(trades)

                observed_ids = get_observed_order_ids(order_book, trades)
                new_order_ids = observed_ids - self._seen_order_ids
                self._seen_order_ids.update(new_order_ids)

                now = time.monotonic()
                for _ in new_order_ids:
                    self._recent_order_times.append(now)

                while (
                    self._recent_order_times
                    and now - self._recent_order_times[0] >= OPS_WINDOW_SECONDS
                ):
                    self._recent_order_times.popleft()

                # Copy engine data before publishing it to the UI thread.
                book_copy = {
                    "buys": [dict(order) for order in order_book.get("buys", [])],
                    "sells": [dict(order) for order in order_book.get("sells", [])],
                }
                with self._lock:
                    self._snapshot = {
                        "order_book": book_copy,
                        "recent_trades": list(self._recent_trades),
                        "ops": len(self._recent_order_times),
                        "latency_stats": latency_stats,
                        "error": None,
                    }

            except Exception as exc:
                with self._lock:
                    self._snapshot["error"] = str(exc)

            self._stop_event.wait(ENGINE_POLL_INTERVAL_SECONDS)


def safe_addstr(window, y, x, text):
    """Write text without exceeding the current terminal boundaries."""
    height, width = window.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= width - 1:
        return
    try:
        window.addnstr(y, x, str(text), max(0, width - x - 1))
    except curses.error:
        pass


def draw_latency_window(stdscr, latency_stats):
    safe_addstr(
        stdscr, 2, 2,
        "ENGINE SNAPSHOT POLLING LATENCY (microseconds)"
    )
    if latency_stats is None:
        safe_addstr(stdscr, 3, 2, "Collecting initial clock samples...")
        safe_addstr(stdscr, 4, 2, "P50: --    P95: --    P99: --")
        return

    safe_addstr(
        stdscr, 3, 2,
        f"MIN: {latency_stats['min']:.2f} us  "
        f"AVG: {latency_stats['avg']:.2f} us  "
        f"MAX: {latency_stats['max']:.2f} us"
    )
    safe_addstr(
        stdscr, 4, 2,
        f"P50: {latency_stats['p50']:.2f} us  "
        f"P95: {latency_stats['p95']:.2f} us  "
        f"P99: {latency_stats['p99']:.2f} us"
    )


def draw_trade_window(stdscr, recent_trades, start_row):
    height, _ = stdscr.getmaxyx()
    if start_row >= height - 1:
        return

    safe_addstr(stdscr, start_row, 2, "EXECUTED TRADES - LATEST FIRST")
    safe_addstr(stdscr, start_row + 1, 2, "-" * 55)

    available_rows = max(0, height - start_row - 3)
    visible_trades = (
        list(reversed(list(recent_trades)[-available_rows:]))
        if available_rows else []
    )

    if not visible_trades:
        safe_addstr(stdscr, start_row + 2, 2, "No executed trades yet.")
        return

    for offset, trade in enumerate(visible_trades):
        try:
            price = float(trade.get("price", 0))
        except (TypeError, ValueError):
            price = 0.0
        safe_addstr(
            stdscr, start_row + 2 + offset, 2,
            f"Buy:{trade.get('buy_order_id', '?')} "
            f"Sell:{trade.get('sell_order_id', '?')} "
            f"Price:{price:.2f} Qty:{trade.get('quantity', '?')}"
        )


def draw_layout(
    stdscr, order_book=None, ops=0, recent_trades=None,
    latency_stats=None, error=None,
):
    """Render the dashboard on the curses/UI thread only."""
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    stdscr.erase()
    height, width = stdscr.getmaxyx()
    order_book = order_book or {"buys": [], "sells": []}
    recent_trades = recent_trades or []

    safe_addstr(stdscr, 0, 0, " ChronosEngine - Matching Engine Dashboard ")
    safe_addstr(stdscr, 1, 2, f"ORDERS/SEC (OPS): {ops}")

    if error:
        safe_addstr(stdscr, 5, 2, f"ENGINE WORKER ERROR: {error}")

    if height < 19 or width < 64:
        safe_addstr(
            stdscr, 6, 2,
            "Enlarge terminal to at least 64 columns and 19 rows."
        )
        if height > 1:
            safe_addstr(stdscr, height - 1, 0, "Press Q to quit")
        stdscr.refresh()
        return

    draw_latency_window(stdscr, latency_stats)

    bids = aggregate_depth(order_book.get("buys", []))
    asks = aggregate_depth(order_book.get("sells", []))
    bid_prices = sorted(bids, reverse=True)[:DEPTH_LEVELS]
    ask_prices = sorted(asks)[:DEPTH_LEVELS]

    best_bid = bid_prices[0] if bid_prices else None
    best_ask = ask_prices[0] if ask_prices else None

    bid_text = (
        f"{best_bid:.2f} (Qty: {bids[best_bid]['quantity']})"
        if best_bid is not None else "--"
    )
    ask_text = (
        f"{best_ask:.2f} (Qty: {asks[best_ask]['quantity']})"
        if best_ask is not None else "--"
    )

    safe_addstr(stdscr, 6, 2, "TOP OF BOOK")
    safe_addstr(
        stdscr, 7, 2,
        f"BEST BID: {bid_text}    |    BEST ASK: {ask_text}"
    )
    safe_addstr(stdscr, 9, 2, f"ORDER BOOK DEPTH - TOP {DEPTH_LEVELS} LEVELS")
    safe_addstr(stdscr, 10, 2, "-" * min(width - 4, 60))
    safe_addstr(
        stdscr, 11, 2,
        f"{'BID PRICE':>12} {'BID QTY':>9} {'N':>3} | "
        f"{'ASK PRICE':>12} {'ASK QTY':>9} {'N':>3}"
    )

    visible_levels = min(DEPTH_LEVELS, max(1, height - 19))
    for level in range(visible_levels):
        bp = bid_prices[level] if level < len(bid_prices) else None
        ap = ask_prices[level] if level < len(ask_prices) else None
        bid = (
            f"{bp:>12.2f} {bids[bp]['quantity']:>9} "
            f"{bids[bp]['orders']:>3}"
            if bp is not None else f"{'--':>12} {'--':>9} {'--':>3}"
        )
        ask = (
            f"{ap:>12.2f} {asks[ap]['quantity']:>9} "
            f"{asks[ap]['orders']:>3}"
            if ap is not None else f"{'--':>12} {'--':>9} {'--':>3}"
        )
        safe_addstr(stdscr, 12 + level, 2, f"{bid} | {ask}")

    trade_top = 13 + visible_levels
    draw_trade_window(stdscr, recent_trades, trade_top)

    safe_addstr(stdscr, height - 1, 0, "Press Q to quit")
    stdscr.refresh()


def main(stdscr, engine=None):
    """Run curses independently from the engine snapshot polling thread."""
    if engine is None:
        engine = MatchingEngine()

    stdscr.timeout(REFRESH_INTERVAL_MS)
    worker = EngineSnapshotWorker(engine)
    worker.start()

    try:
        while True:
            snapshot = worker.get_latest_snapshot()
            draw_layout(
                stdscr,
                order_book=snapshot["order_book"],
                ops=snapshot["ops"],
                recent_trades=snapshot["recent_trades"],
                latency_stats=snapshot["latency_stats"],
                error=snapshot["error"],
            )

            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                break

            if key == curses.KEY_RESIZE:
                if hasattr(curses, "update_lines_cols"):
                    curses.update_lines_cols()
                stdscr.clearok(True)
                stdscr.erase()

    finally:
        worker.stop()


if __name__ == "__main__":
    curses.wrapper(main)
