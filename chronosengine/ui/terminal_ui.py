
import argparse
import curses
import time
from collections import deque


DEPTH_LEVELS = 5
REFRESH_INTERVAL_MS = 250
OPS_WINDOW_SECONDS = 1.0

# 50 microseconds = 50,000 nanoseconds
SLA_THRESHOLD_NS = 50_000


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="ChronosEngine terminal matching engine dashboard"
    )
    parser.add_argument(
        "--refresh-ms",
        type=int,
        default=250,
        help="Dashboard refresh interval in milliseconds (default: 250)"
    )
    parser.add_argument(
        "--depth-levels",
        type=int,
        default=5,
        help="Number of order book levels to display (default: 5)"
    )
    parser.add_argument(
        "--ops-window",
        type=float,
        default=1.0,
        help="OPS measurement window in seconds (default: 1.0)"
    )

    options = parser.parse_args(args)

    if options.refresh_ms <= 0:
        parser.error("--refresh-ms must be greater than zero")
    if options.depth_levels <= 0:
        parser.error("--depth-levels must be greater than zero")
    if options.ops_window <= 0:
        parser.error("--ops-window must be greater than zero")

    return options


def safe_addstr(stdscr, y, x, text, attr=0):
    height, width = stdscr.getmaxyx()

    if y < 0 or y >= height or x < 0 or x >= width - 1:
        return

    try:
        stdscr.addnstr(
            y,
            x,
            str(text),
            width - x - 1,
            attr
        )
    except curses.error:
        pass


def get_observed_order_ids(order_book, trades):
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



def get_active_orders(order_book):
    """Return active orders indexed by their unique order IDs."""
    active = {}

    for side in ("buys", "sells"):
        for order in order_book.get(side, []):
            active[order["order_id"]] = order

    return active


def get_best_spread(order_book):
    """Return best ask minus best bid, or None if either side is empty."""
    bids = order_book.get("buys", [])
    asks = order_book.get("sells", [])

    if not bids or not asks:
        return None

    best_bid = max(float(order["price"]) for order in bids)
    best_ask = min(float(order["price"]) for order in asks)

    return best_ask - best_bid


def detect_order_events(
    previous_order_book,
    current_order_book,
    previous_trade_count,
    trades,
    previous_spread,
):
    """Detect fills, cancellations, and changes in the bid-ask spread."""
    events = []

    new_trades = (
        trades[previous_trade_count:]
        if len(trades) >= previous_trade_count
        else trades
    )

    filled_order_ids = set()

    for trade in new_trades:
        buy_id = trade.get("buy_order_id")
        sell_id = trade.get("sell_order_id")

        if buy_id is not None:
            filled_order_ids.add(buy_id)

        if sell_id is not None:
            filled_order_ids.add(sell_id)

        events.append({
            "type": "FILL",
            "text": (
                f"FILL | Buy #{buy_id} / Sell #{sell_id} "
                f"| Qty: {trade.get('quantity', 0)} "
                f"| Price: {trade.get('price', 0)}"
            ),
        })

    if previous_order_book is not None:
        previous_orders = get_active_orders(previous_order_book)
        current_orders = get_active_orders(current_order_book)

        disappeared_ids = (
            set(previous_orders) - set(current_orders)
        )

        for order_id in sorted(disappeared_ids, key=str):
            if order_id not in filled_order_ids:
                events.append({
                    "type": "CANCEL",
                    "text": f"CANCEL | Order #{order_id}",
                })

    current_spread = get_best_spread(current_order_book)

    if (
        previous_spread is not None
        and current_spread is not None
        and current_spread != previous_spread
    ):
        events.append({
            "type": "SPREAD",
            "text": (
                f"SPREAD SHIFT | {previous_spread:.2f} "
                f"-> {current_spread:.2f}"
            ),
        })

    return events, len(trades), current_spread


def draw_event_status(stdscr, events):
    """Display the latest order-state event using its assigned color."""
    if not events:
        safe_addstr(stdscr, 4, 2, "LATEST EVENT: Waiting for order activity")
        return

    event = events[-1]
    event_type = event["type"]

    color_pairs = {
        "FILL": 2,
        "CANCEL": 1,
        "SPREAD": 3,
    }

    attr = curses.A_BOLD

    try:
        if curses.has_colors():
            attr |= curses.color_pair(color_pairs[event_type])
    except curses.error:
        pass

    safe_addstr(
        stdscr,
        4,
        2,
        event["text"],
        attr,
    )


def count_sla_breaches(samples_ns, threshold_ns=SLA_THRESHOLD_NS):
    """
    Count latency samples exceeding the SLA threshold.

    Default threshold: 50,000 ns (50 microseconds).
    Exactly 50,000 ns is not considered a breach.
    """

    if (
        isinstance(threshold_ns, bool)
        or not isinstance(threshold_ns, int)
        or threshold_ns < 0
    ):
        raise ValueError(
            "threshold_ns must be a non-negative integer"
        )

    samples = list(samples_ns)

    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        for value in samples
    ):
        raise ValueError(
            "Latency samples must be non-negative integers"
        )

    return sum(
        1 for latency in samples
        if latency > threshold_ns
    )


def build_latency_histogram(samples_ns, bucket_count=5, bar_width=24):
    """Build an ASCII histogram from actual latency samples."""

    if bucket_count <= 0 or bar_width <= 0:
        raise ValueError(
            "bucket_count and bar_width must be positive"
        )

    samples = list(samples_ns)

    if not samples:
        return []

    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        for value in samples
    ):
        raise ValueError(
            "Latency samples must be non-negative integers"
        )

    max_latency = max(samples)

    bucket_width = max(
        1,
        (max_latency + 1 + bucket_count - 1) // bucket_count,
    )

    counts = [0] * bucket_count

    for latency in samples:
        index = min(
            latency // bucket_width,
            bucket_count - 1
        )
        counts[index] += 1

    max_count = max(counts)
    histogram = []

    for index, count in enumerate(counts):
        lower = index * bucket_width
        upper = (index + 1) * bucket_width

        bar_length = round(
            count / max_count * bar_width
        )

        label = (
            f"{lower / 1000:.2f}-{upper / 1000:.2f} us"
        )

        histogram.append({
            "label": label,
            "count": count,
            "bar": "#" * bar_length,
        })

    return histogram


def draw_sla_indicator(stdscr, samples, start_y):
    """Display rolling SLA breach count and visual warning."""

    breach_count = count_sla_breaches(samples)

    if breach_count > 0:
        warning_text = (
            f"!!! SLA BREACH: {breach_count} samples "
            f"exceeded 50 us !!!"
        )

        warning_attr = curses.A_BOLD

        try:
            if curses.has_colors():
                warning_attr = (
                    curses.color_pair(1) | curses.A_BOLD
                )
        except curses.error:
            pass

        safe_addstr(
            stdscr,
            start_y,
            2,
            warning_text,
            warning_attr
        )

    else:
        safe_addstr(
            stdscr,
            start_y,
            2,
            "SLA STATUS: NORMAL - No breaches above 50 us",
            curses.A_BOLD
        )

    safe_addstr(
        stdscr,
        start_y + 1,
        2,
        f"SLA THRESHOLD: 50.00 us | "
        f"BREACH COUNT: {breach_count}",
    )


def draw_latency_panel(stdscr, metrics, start_y):
    """Render latency histogram, percentiles and SLA indicator."""

    samples = metrics.get("latency_samples_ns", [])
    histogram = build_latency_histogram(samples)

    safe_addstr(
        stdscr,
        start_y,
        2,
        "LATENCY DISTRIBUTION (ASCII HISTOGRAM)",
    )

    if not histogram:
        safe_addstr(
            stdscr,
            start_y + 1,
            2,
            "Waiting for latency samples..."
        )

        draw_sla_indicator(
            stdscr,
            samples,
            start_y + 2
        )
        return

    for index, bucket in enumerate(histogram):
        line = (
            f"{bucket['label']:>17} | "
            f"{bucket['bar']:<24} {bucket['count']}"
        )

        safe_addstr(
            stdscr,
            start_y + 1 + index,
            2,
            line
        )

    p50 = metrics.get("p50_latency_ns", 0) / 1000
    p90 = metrics.get("p90_latency_ns", 0) / 1000
    p99 = metrics.get("p99_latency_ns", 0) / 1000
    p999 = metrics.get("p999_latency_ns", 0) / 1000

    safe_addstr(
        stdscr,
        start_y + 6,
        2,
        f"P50: {p50:.2f}  P90: {p90:.2f}  "
        f"P99: {p99:.2f}  P999: {p999:.2f} us",
    )

    safe_addstr(
        stdscr,
        start_y + 7,
        2,
        f"Samples: {metrics.get('latency_sample_count', len(samples))}",
    )

    draw_sla_indicator(
        stdscr,
        samples,
        start_y + 8
    )


def draw_layout(
    stdscr,
    order_book=None,
    ops=0,
    depth_levels=DEPTH_LEVELS,
    latency_metrics=None,
    events=None
):
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
        " ChronosEngine - Matching Engine Dashboard "
    )

    safe_addstr(
        stdscr,
        1,
        2,
        f"ORDERS/SEC (OPS): {ops}"
    )

    if order_book is None:
        order_book = {
            "buys": [],
            "sells": []
        }

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
    draw_event_status(stdscr, events or [])

    if height >= 12 and width >= 64:
        safe_addstr(
            stdscr,
            2,
            2,
            "TOP OF BOOK"
        )

        bid_text = (
            f"{best_bid['price']:.2f} "
            f"(Qty: {best_bid['quantity']})"
            if best_bid else "--"
        )

        ask_text = (
            f"{best_ask['price']:.2f} "
            f"(Qty: {best_ask['quantity']})"
            if best_ask else "--"
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
            f"ORDER BOOK DEPTH - TOP {depth_levels} LEVELS",
        )

        safe_addstr(
            stdscr,
            6,
            2,
            "-" * min(width - 4, 60)
        )

        safe_addstr(
            stdscr,
            7,
            2,
            f"{'BID PRICE':>12} {'BID QTY':>9}  |  "
            f"{'ASK PRICE':>12} {'ASK QTY':>9}",
        )

        safe_addstr(
            stdscr,
            8,
            2,
            "-" * min(width - 4, 60)
        )

        if height >= 24:
            visible_levels = min(
                depth_levels,
                max(0, height - 20)
            )
        else:
            visible_levels = min(
                depth_levels,
                max(0, height - 10)
            )

        if not bids and not asks:
            safe_addstr(
                stdscr,
                9,
                2,
                "Order book is empty."
            )

        else:
            for level in range(visible_levels):
                bid = (
                    bids[level]
                    if level < len(bids)
                    else None
                )

                ask = (
                    asks[level]
                    if level < len(asks)
                    else None
                )

                bid_price = (
                    f"{bid['price']:>12.2f}"
                    if bid else f"{'--':>12}"
                )

                bid_qty = (
                    f"{bid['quantity']:>9}"
                    if bid else f"{'--':>9}"
                )

                ask_price = (
                    f"{ask['price']:>12.2f}"
                    if ask else f"{'--':>12}"
                )

                ask_qty = (
                    f"{ask['quantity']:>9}"
                    if ask else f"{'--':>9}"
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

    # Keep histogram and SLA panel separate from the order book.
    if (
        latency_metrics is not None
        and height >= 24
        and width >= 64
    ):
        draw_latency_panel(
            stdscr,
            latency_metrics,
            height - 12
        )

    if height > 1:
        safe_addstr(
            stdscr,
            height - 1,
            0,
            "Press Q to quit"
        )

    stdscr.refresh()


def main(stdscr, engine=None, options=None):
    if engine is None:
        from chronosengine.matching_engine import MatchingEngine
        engine = MatchingEngine()

    if options is None:
        options = parse_args([])

    # Initialize terminal colors before using curses color pairs.
    try:
        curses.start_color()
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    except curses.error:
        pass

    stdscr.timeout(options.refresh_ms)

    seen_order_ids = set()
    recent_order_times = deque()
    event_log = deque(maxlen=5)
    previous_order_book = engine.get_order_book()
    previous_trades = engine.get_trades()
    previous_trade_count = len(previous_trades)
    previous_spread = get_best_spread(previous_order_book)

    while True:
        now = time.monotonic()

        order_book = engine.get_order_book()
        trades = engine.get_trades()

        new_events, previous_trade_count, previous_spread = (
            detect_order_events(
                previous_order_book,
                order_book,
                previous_trade_count,
                trades,
                previous_spread,
            )
        )
        event_log.extend(new_events)
        previous_order_book = order_book

        observed_ids = get_observed_order_ids(
            order_book,
            trades
        )

        new_order_ids = observed_ids - seen_order_ids
        seen_order_ids.update(new_order_ids)

        for _ in new_order_ids:
            recent_order_times.append(now)

        while (
            recent_order_times
            and now - recent_order_times[0] >= options.ops_window
        ):
            recent_order_times.popleft()

        ops = int(
            len(recent_order_times) / options.ops_window
        )

        latency_metrics = engine.get_latency_metrics()

        draw_layout(
            stdscr,
            order_book,
            ops,
            options.depth_levels,
            latency_metrics,
            list(event_log),
        )

        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            break

        if key == curses.KEY_RESIZE:
            if hasattr(curses, "update_lines_cols"):
                curses.update_lines_cols()

            stdscr.clearok(True)
            stdscr.erase()


def launch_dashboard(options, engine=None):
    if engine is None:
        from chronosengine.matching_engine import MatchingEngine
        engine = MatchingEngine()

    curses.wrapper(
        lambda stdscr: main(stdscr, engine, options)
    )


if __name__ == "__main__":
    cli_options = parse_args()
    launch_dashboard(cli_options)
