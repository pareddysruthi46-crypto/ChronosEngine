
import curses

from chronosengine.matching_engine import MatchingEngine


DEPTH_LEVELS = 5


def safe_addstr(stdscr, y, x, text):
    """Write text without exceeding the terminal boundaries."""
    height, width = stdscr.getmaxyx()

    if y < 0 or y >= height or x < 0 or x >= width - 1:
        return

    available = width - x - 1

    try:
        stdscr.addnstr(y, x, str(text), available)
    except curses.error:
        pass


def draw_layout(stdscr, order_book=None):
    """Render top-of-book information and a multi-level depth ladder."""
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    stdscr.erase()
    height, width = stdscr.getmaxyx()

    safe_addstr(stdscr, 0, 0, " ChronosEngine - Matching Engine Dashboard ")

    if order_book is None:
        order_book = {"buys": [], "sells": []}

    # Sort bids from highest to lowest and asks from lowest to highest.
    bids = sorted(
        order_book.get("buys", []),
        key=lambda order: float(order["price"]),
        reverse=True,
    )
    asks = sorted(
        order_book.get("sells", []),
        key=lambda order: float(order["price"]),
    )

    # Top-of-book values.
    best_bid = bids[0] if bids else None
    best_ask = asks[0] if asks else None

    if height >= 12 and width >= 64:
        safe_addstr(stdscr, 2, 2, "TOP OF BOOK")

        bid_text = (
            f"{best_bid['price']:.2f} (Qty: {best_bid['quantity']})"
            if best_bid else "--"
        )
        ask_text = (
            f"{best_ask['price']:.2f} (Qty: {best_ask['quantity']})"
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

        # Display as many levels as the terminal height allows, up to five.
        visible_levels = min(DEPTH_LEVELS, max(0, height - 10))

        if not bids and not asks:
            safe_addstr(stdscr, 9, 2, "Order book is empty.")
        else:
            for level in range(visible_levels):
                bid = bids[level] if level < len(bids) else None
                ask = asks[level] if level < len(asks) else None

                bid_price = f"{bid['price']:>12.2f}" if bid else f"{'--':>12}"
                bid_qty = f"{bid['quantity']:>9}" if bid else f"{'--':>9}"
                ask_price = f"{ask['price']:>12.2f}" if ask else f"{'--':>12}"
                ask_qty = f"{ask['quantity']:>9}" if ask else f"{'--':>9}"

                safe_addstr(
                    stdscr, 9 + level, 2,
                    f"{bid_price} {bid_qty}  |  {ask_price} {ask_qty}",
                )
    else:
        safe_addstr(
            stdscr, 2, 0,
            "Enlarge terminal to at least 64 columns and 12 rows.",
        )

    if height > 1:
        safe_addstr(stdscr, height - 1, 0, "Press Q to quit")

    stdscr.refresh()


def main(stdscr, engine=None):
    """Run the dashboard using the supplied matching engine."""
    if engine is None:
        engine = MatchingEngine()

    while True:
        draw_layout(stdscr, engine.get_order_book())
        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            break


if __name__ == "__main__":
    curses.wrapper(main)
