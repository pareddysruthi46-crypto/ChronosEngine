
import curses
import time
from collections import deque

from chronosengine.matching_engine import MatchingEngine

DEPTH_LEVELS = 5
REFRESH_INTERVAL_MS = 250
OPS_WINDOW_SECONDS = 1.0
TRADE_BUFFER_SIZE = 8


def safe_addstr(window, y, x, text):
    """Write text safely within terminal boundaries."""
    height, width = window.getmaxyx()

    if y < 0 or y >= height or x < 0 or x >= width - 1:
        return

    try:
        window.addnstr(y, x, str(text), max(0, width - x - 1))
    except curses.error:
        pass


def get_observed_order_ids(order_book, trades):
    """Collect order IDs from the book and completed trades."""
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


def draw_trade_window(stdscr, recent_trades, start_row):
    """Display executed trades directly on the main screen."""
    height, _ = stdscr.getmaxyx()

    if start_row >= height - 1:
        return

    safe_addstr(stdscr, start_row, 2, "EXECUTED TRADES - LATEST FIRST")
    safe_addstr(stdscr, start_row + 1, 2, "-" * 55)

    available_rows = max(0, height - start_row - 3)
    trades = list(recent_trades)
    visible_trades = (
        list(reversed(trades[-available_rows:]))
        if available_rows else []
    )

    if not visible_trades:
        safe_addstr(stdscr, start_row + 2, 2, "No executed trades yet.")
        return

    for offset, trade in enumerate(visible_trades):
        row = start_row + 2 + offset

        try:
            price = float(trade.get("price", 0))
        except (TypeError, ValueError):
            price = 0.0

        text = (
            f"Buy:{trade.get('buy_order_id', '?')} "
            f"Sell:{trade.get('sell_order_id', '?')} "
            f"Price:{price:.2f} "
            f"Qty:{trade.get('quantity', '?')}"
        )

        safe_addstr(stdscr, row, 2, text)


def draw_layout(stdscr, order_book=None, ops=0, recent_trades=None):
    """Draw the dashboard, order book and executed trades."""
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    stdscr.erase()
    height, width = stdscr.getmaxyx()

    if order_book is None:
        order_book = {"buys": [], "sells": []}

    if recent_trades is None:
        recent_trades = []

    safe_addstr(stdscr, 0, 0, " ChronosEngine - Matching Engine Dashboard ")
    safe_addstr(stdscr, 1, 2, f"ORDERS/SEC (OPS): {ops}")

    if height < 16 or width < 64:
        safe_addstr(
            stdscr, 3, 2,
            "Enlarge terminal to at least 64 columns and 16 rows."
        )
        safe_addstr(stdscr, height - 1, 0, "Press Q to quit")
        stdscr.refresh()
        return

    bids = sorted(
        order_book.get("buys", []),
        key=lambda order: float(order["price"]),
        reverse=True,
    )
    asks = sorted(
        order_book.get("sells", []),
        key=lambda order: float(order["price"]),
    )

    best_bid = bids[0] if bids else None
    best_ask = asks[0] if asks else None

    bid_text = (
        f"{float(best_bid['price']):.2f} (Qty: {best_bid['quantity']})"
        if best_bid else "--"
    )
    ask_text = (
        f"{float(best_ask['price']):.2f} (Qty: {best_ask['quantity']})"
        if best_ask else "--"
    )

    safe_addstr(stdscr, 2, 2, "TOP OF BOOK")
    safe_addstr(
        stdscr, 3, 2,
        f"BEST BID: {bid_text}    |    BEST ASK: {ask_text}"
    )

    safe_addstr(stdscr, 5, 2, f"ORDER BOOK DEPTH - TOP {DEPTH_LEVELS} LEVELS")
    safe_addstr(stdscr, 6, 2, "-" * min(width - 4, 60))
    safe_addstr(
        stdscr, 7, 2,
        f"{'BID PRICE':>12} {'BID QTY':>9}  |  "
        f"{'ASK PRICE':>12} {'ASK QTY':>9}"
    )
    safe_addstr(stdscr, 8, 2, "-" * min(width - 4, 60))

    # Reserve rows below the order book for executed trades.
    visible_levels = min(DEPTH_LEVELS, max(1, height - 15))

    for level in range(visible_levels):
        bid = bids[level] if level < len(bids) else None
        ask = asks[level] if level < len(asks) else None

        bid_price = f"{float(bid['price']):>12.2f}" if bid else f"{'--':>12}"
        bid_qty = f"{bid['quantity']:>9}" if bid else f"{'--':>9}"
        ask_price = f"{float(ask['price']):>12.2f}" if ask else f"{'--':>12}"
        ask_qty = f"{ask['quantity']:>9}" if ask else f"{'--':>9}"

        safe_addstr(
            stdscr, 9 + level, 2,
            f"{bid_price} {bid_qty}  |  {ask_price} {ask_qty}"
        )

    trade_top = 10 + visible_levels
    draw_trade_window(stdscr, recent_trades, trade_top)

    safe_addstr(stdscr, height - 1, 0, "Press Q to quit")
    stdscr.refresh()


def main(stdscr, engine=None):
    """Run the live matching-engine dashboard."""
    if engine is None:
        engine = MatchingEngine()

    stdscr.timeout(REFRESH_INTERVAL_MS)

    recent_trades = deque(maxlen=TRADE_BUFFER_SIZE)
    recent_order_times = deque()
    seen_order_ids = set()
    last_trade_count = 0

    while True:
        now = time.monotonic()
        order_book = engine.get_order_book()
        trades = list(engine.get_trades())

        # Handle trade history reset.
        if len(trades) < last_trade_count:
            last_trade_count = 0
            recent_trades.clear()

        for trade in trades[last_trade_count:]:
            recent_trades.append(trade)

        last_trade_count = len(trades)

        observed_ids = get_observed_order_ids(order_book, trades)
        new_order_ids = observed_ids - seen_order_ids
        seen_order_ids.update(new_order_ids)

        for _ in new_order_ids:
            recent_order_times.append(now)

        while (
            recent_order_times
            and now - recent_order_times[0] >= OPS_WINDOW_SECONDS
        ):
            recent_order_times.popleft()

        draw_layout(
            stdscr, order_book, len(recent_order_times), recent_trades
        )

        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            break

        if key == curses.KEY_RESIZE:
            if hasattr(curses, "update_lines_cols"):
                curses.update_lines_cols()
            stdscr.clearok(True)
            stdscr.erase()


if __name__ == "__main__":
    curses.wrapper(main)
