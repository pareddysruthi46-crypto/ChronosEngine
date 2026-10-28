
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


def aggregate_depth(orders):
    """Aggregate quantity and order count for each price."""
    levels = {}
    for order in orders:
        price = float(order["price"])
        if price not in levels:
            levels[price] = {"quantity": 0, "orders": 0}
        levels[price]["quantity"] += int(order["quantity"])
        levels[price]["orders"] += 1
    return levels


def draw_layout(stdscr, order_book, ops, recent_trades):
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    stdscr.erase()
    height, width = stdscr.getmaxyx()

    safe_addstr(stdscr, 0, 0, " ChronosEngine - Live Matching Dashboard ")
    safe_addstr(stdscr, 1, 2, f"NEW TRADES/SEC: {ops}")

    bids = aggregate_depth(order_book.get("buys", []))
    asks = aggregate_depth(order_book.get("sells", []))
    bid_prices = sorted(bids, reverse=True)[:DEPTH_LEVELS]
    ask_prices = sorted(asks)[:DEPTH_LEVELS]

    if height >= 12 and width >= 64:
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

        safe_addstr(stdscr, 2, 2, "TOP OF BOOK")
        safe_addstr(stdscr, 3, 2, f"BEST BID: {bid_text} | BEST ASK: {ask_text}")
        safe_addstr(stdscr, 5, 2, "AGGREGATED ORDER BOOK DEPTH")
        safe_addstr(stdscr, 6, 2, "-" * min(width - 4, 60))
        safe_addstr(
            stdscr, 7, 2,
            f"{'BID PRICE':>12} {'BID QTY':>9} {'N':>3} | "
            f"{'ASK PRICE':>12} {'ASK QTY':>9} {'N':>3}"
        )

        visible = min(DEPTH_LEVELS, max(0, height - 11))
        for i in range(visible):
            bp = bid_prices[i] if i < len(bid_prices) else None
            ap = ask_prices[i] if i < len(ask_prices) else None

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
            safe_addstr(stdscr, 8 + i, 2, f"{bid} | {ask}")

        trade_start = 9 + visible
        safe_addstr(stdscr, trade_start, 2, "RECENT MATCHED TRADES")
        for i, trade in enumerate(recent_trades):
            y = trade_start + 1 + i
            if y >= height - 1:
                break
            safe_addstr(
                stdscr, y, 2,
                f"Buy:{trade.get('buy_order_id', '?')} "
                f"Sell:{trade.get('sell_order_id', '?')} "
                f"Price:{float(trade.get('price', 0)):.2f} "
                f"Qty:{trade.get('quantity', 0)}"
            )
    else:
        safe_addstr(stdscr, 2, 0, "Enlarge terminal to at least 64 columns and 12 rows.")

    if height > 1:
        safe_addstr(stdscr, height - 1, 0, "Press Q to quit")
    stdscr.refresh()


def main(stdscr, engine=None):
    if engine is None:
        engine = MatchingEngine()

    stdscr.timeout(REFRESH_INTERVAL_MS)
    recent_trades = deque(maxlen=TRADE_BUFFER_SIZE)
    recent_trade_times = deque()
    last_trade_count = 0

    while True:
        now = time.monotonic()
        order_book = engine.get_order_book()
        trades = engine.get_trades()

        # Ingest only newly appended trades.
        if len(trades) < last_trade_count:
            last_trade_count = 0

        new_trades = trades[last_trade_count:]
        last_trade_count = len(trades)

        for trade in new_trades:
            recent_trades.append(trade)
            recent_trade_times.append(now)

        while (
            recent_trade_times
            and now - recent_trade_times[0] >= OPS_WINDOW_SECONDS
        ):
            recent_trade_times.popleft()

        draw_layout(stdscr, order_book, len(recent_trade_times), recent_trades)

        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            break

        if key == curses.KEY_RESIZE:
            if hasattr(curses, "update_lines_cols"):
                curses.update_lines_cols()
            stdscr.clearok(True)


if __name__ == "__main__":
    curses.wrapper(main)
