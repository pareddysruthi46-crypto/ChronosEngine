import curses
from collections import deque
from chronosengine.ui.terminal_ui import draw_layout

sample_order_book = {
    "buys": [
        {"order_id": 1, "side": "B", "price": 100.0, "quantity": 5, "timestamp": 1}
    ],
    "sells": []
}

sample_trades = deque([
    {"buy_order_id": 1, "sell_order_id": 2, "price": 100.0, "quantity": 5, "timestamp": 2},
    {"buy_order_id": 3, "sell_order_id": 4, "price": 101.0, "quantity": 2, "timestamp": 3},
], maxlen=8)

def test_ui(stdscr):
    height, width = stdscr.getmaxyx()
    stdscr.erase()
    stdscr.addstr(0, 0, f"Terminal size: {height} rows x {width} columns")
    stdscr.refresh()
    curses.napms(1500)
    draw_layout(stdscr, sample_order_book, 2, sample_trades)
    stdscr.getch()

curses.wrapper(test_ui)
