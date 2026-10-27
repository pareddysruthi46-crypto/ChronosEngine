

import curses
import time
from collections import deque

from chronosengine.matching_engine import MatchingEngine

DEPTH_LEVELS = 5
REFRESH_INTERVAL_MS = 250
OPS_WINDOW_SECONDS = 1.0


def safe_addstr(stdscr, y, x, text):
    """Write text without exceeding terminal boundaries."""
    height, width = stdscr.getmaxyx()

    if y < 0 or y >= height or x < 0 or x >= width - 1:
        return

    available = width - x - 1

    try:
        stdscr.addnstr(y, x, str(text), available)
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


def draw_layout(stdscr, order_book=None, ops=0):
    """Render the order book and live throughput metric."""
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    stdscr.erase()
    height, width = stdscr.getmaxyx()

    safe_addstr(
        stdscr,
        0,
        0,
        " ChronosEngine - Matching Engine Dashboard ",
    )
    safe_addstr(
        stdscr,
        1,
        2,
        f"ORDERS/SEC (OPS): {ops}",
    )

    if order_book is None:
        order_book = {"buys": [], "sells": []}

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
            f"{best_bid['price']:.2f} "
            f"(Qty: {best_bid['quantity']})"
            if best_bid
            else "--"
        )
        ask_text = (
            f"{best_ask['price']:.2f} "
            f"(Qty: {best_ask['quantity']})"
            if best_ask
            else "--"
        )

        safe_addstr(
            stdscr,
            3,
            2,
            f"BEST BID: {bid_text}    |    BEST ASK: {ask_text}",
        )

        safe_addstr(
            stdscr,
            5,
            2,
            f"ORDER BOOK DEPTH - TOP {DEPTH_LEVELS} LEVELS",
        )
        safe_addstr(stdscr, 6, 2, "-" * min(width - 4, 60))

        safe_addstr(
            stdscr,
            7,
            2,
            f"{'BID PRICE':>12} {'BID QTY':>9}  |  "
            f"{'ASK PRICE':>12} {'ASK QTY':>9}",
        )

        safe_addstr(stdscr, 8, 2, "-" * min(width - 4, 60))

        visible_levels = min(DEPTH_LEVELS, max(0, height - 10))

        if not bids and not asks:
            safe_addstr(stdscr, 9, 2, "Order book is empty.")
        else:
            for level in range(visible_levels):
                bid = bids[level] if level < len(bids) else None
                ask = asks[level] if level < len(asks) else None

                bid_price = (
                    f"{bid['price']:>12.2f}"
                    if bid
                    else f"{'--':>12}"
                )
                bid_qty = (
                    f"{bid['quantity']:>9}"
                    if bid
                    else f"{'--':>9}"
                )
                ask_price = (
                    f"{ask['price']:>12.2f}"
                    if ask
                    else f"{'--':>12}"
                )
                ask_qty = (
                    f"{ask['quantity']:>9}"
                    if ask
                    else f"{'--':>9}"
                )

                safe_addstr(
                    stdscr,
                    9 + level,
                    2,
                    f"{bid_price} {bid_qty}  |  "
                    f"{ask_price} {ask_qty}",
                )
    else:
        safe_addstr(
            stdscr,
            2,
            0,
            "Enlarge terminal to at least 64 columns and 12 rows.",
        )

    if height > 1:
        safe_addstr(stdscr, height - 1, 0, "Press Q to quit")

    stdscr.refresh()


def main(stdscr, engine=None):
    """Run the dashboard and handle terminal resize events."""
    if engine is None:
        engine = MatchingEngine()

    # Refresh automatically, even when no key is pressed.
    stdscr.timeout(REFRESH_INTERVAL_MS)

    seen_order_ids = set()
    recent_order_times = deque()

    while True:
        now = time.monotonic()

        order_book = engine.get_order_book()
        trades = engine.get_trades()

        observed_ids = get_observed_order_ids(order_book, trades)

        # Count each order ID only the first time it becomes observable.
        new_order_ids = observed_ids - seen_order_ids
        seen_order_ids.update(new_order_ids)

        for _ in new_order_ids:
            recent_order_times.append(now)

        # Keep only orders observed during the last second.
        while (
            recent_order_times
            and now - recent_order_times[0] >= OPS_WINDOW_SECONDS
        ):
            recent_order_times.popleft()

        ops = len(recent_order_times)

        # Draw the dashboard using the current terminal dimensions.
        draw_layout(stdscr, order_book, ops)

        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            break

        # Handle terminal resize events and redraw the screen.
        if key == curses.KEY_RESIZE:
            if hasattr(curses, "update_lines_cols"):
                curses.update_lines_cols()

            stdscr.clearok(True)
            stdscr.erase()

            # draw_layout() redraws using the new terminal dimensions.
            draw_layout(stdscr, order_book, ops)


if __name__ == "__main__":
    curses.wrapper(main)
