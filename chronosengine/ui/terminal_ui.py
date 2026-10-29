
import curses
import time
from collections import deque

from chronosengine.matching_engine import MatchingEngine

DEPTH_LEVELS = 5
REFRESH_INTERVAL_MS = 250
OPS_WINDOW_SECONDS = 1.0
TRADE_BUFFER_SIZE = 8


def safe_addstr(stdscr, y, x, text):
    height, width = stdscr.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= width - 1:
        return
    try:
        stdscr.addnstr(y, x, str(text), width - x - 1)
    except curses.error:
        pass


def get_observed_order_ids(order_book, trades):
    """Collect order IDs visible in the book and completed trades."""
    order_ids = set()

    for side in ("buys", "sells"):
        for order in order_book.get(side, []):
            order_ids.add(order["order_id"])

    for trade in trades:
        if "buy_order_id" in trade:
            order_ids.add(trade["buy_order_id"])
        if "sell_order_id" in trade:
            order_ids.add(trade["sell_order_id"])

    return order_ids


def draw_layout(stdscr, order_book=None, ops=0, recent_trades=None):
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    if order_book is None:
        order_book = {"buys": [], "sells": []}
    if recent_trades is None:
        recent_trades = []

    stdscr.erase()
    height, width = stdscr.getmaxyx()

    safe_addstr(stdscr, 0, 0, " ChronosEngine - Matching Engine Dashboard ")
    safe_addstr(stdscr, 1, 2, f"ORDERS/SEC (OPS): {ops}")

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

    if height >= 12 and width >= 64:
        safe_addstr(stdscr, 2, 2, "TOP OF BOOK")

        bid_text = (
            f"{float(best_bid['price']):.2f} (Qty: {best_bid['quantity']})"
            if best_bid else "--"
        )
        ask_text = (
            f"{float(best_ask['price']):.2f} (Qty: {best_ask['quantity']})"
            if best_ask else "--"
        )

        safe_addstr(
            stdscr, 3, 2,
            f"BEST BID: {bid_text}    |    BEST ASK: {ask_text}",
        )
        safe_addstr(stdscr, 5, 2, f"ORDER BOOK DEPTH - TOP {DEPTH_LEVELS} LEVELS")
        safe_addstr(stdscr, 6, 2, "-" * min(width - 4, 60))
        safe_addstr(
            stdscr, 7, 2,
            f"{'BID PRICE':>12} {'BID QTY':>9}  |  "
            f"{'ASK PRICE':>12} {'ASK QTY':>9}",
        )

        safe_addstr(stdscr, 8, 2, "-" * min(width - 4, 60))

        visible_levels = min(DEPTH_LEVELS, max(0, height - 14))

        for level in range(visible_levels):
            bid = bids[level] if level < len(bids) else None
            ask = asks[level] if level < len(asks) else None

            bid_price = f"{float(bid['price']):>12.2f}" if bid else f"{'--':>12}"
            bid_qty = f"{bid['quantity']:>9}" if bid else f"{'--':>9}"
            ask_price = f"{float(ask['price']):>12.2f}" if ask else f"{'--':>12}"
            ask_qty = f"{ask['quantity']:>9}" if ask else f"{'--':>9}"

            safe_addstr(
                stdscr, 9 + level, 2,
                f"{bid_price} {bid_qty}  |  {ask_price} {ask_qty}",
            )

        trade_start = 10 + visible_levels
        safe_addstr(stdscr, trade_start, 2, "EXECUTED TRADES - LATEST FIRST WINDOW")

        trade_rows = max(0, height - trade_start - 2)
        visible_trades = list(recent_trades)[-trade_rows:] if trade_rows else []

        for index, trade in enumerate(visible_trades):
            y = trade_start + 1 + index
            safe_addstr(
                stdscr, y, 2,
                f"Buy:{trade.get('buy_order_id', '?')} "
                f"Sell:{trade.get('sell_order_id', '?')} "
                f"Price:{float(trade.get('price', 0)):.2f} "
                f"Qty:{trade.get('quantity', 0)}",
            )
    else:
        safe_addstr(stdscr, 2, 0, "Enlarge terminal to at least 64 columns and 12 rows.")

    if height > 1:
        safe_addstr(stdscr, height - 1, 0, "Press Q to quit")
    stdscr.refresh()


def main(stdscr, engine=None):
    """Run the dashboard, live metrics, trade log and resize handling."""
    if engine is None:
        engine = MatchingEngine()

    stdscr.timeout(REFRESH_INTERVAL_MS)

    recent_trades = deque(maxlen=TRADE_BUFFER_SIZE)
    recent_trade_times = deque()
    recent_order_times = deque()
    seen_order_ids = set()
    last_trade_count = 0

    while True:
        now = time.monotonic()
        order_book = engine.get_order_book()
        trades = engine.get_trades()

        # Track newly appended trade records for the scrolling log.
        if len(trades) < last_trade_count:
            last_trade_count = 0

        new_trades = trades[last_trade_count:]
        last_trade_count = len(trades)

        for trade in new_trades:
            recent_trades.append(trade)
            recent_trade_times.append(now)

        # Preserve the original OPS metric based on newly observed order IDs.
        observed_ids = get_observed_order_ids(order_book, trades)
        new_order_ids = observed_ids - seen_order_ids
        seen_order_ids.update(new_order_ids)

        for _ in new_order_ids:
            recent_order_times.append(now)

        while recent_order_times and now - recent_order_times[0] >= OPS_WINDOW_SECONDS:
            recent_order_times.popleft()

        while recent_trade_times and now - recent_trade_times[0] >= OPS_WINDOW_SECONDS:
            recent_trade_times.popleft()

        draw_layout(
            stdscr,
            order_book,
            len(recent_order_times),
            recent_trades,
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
