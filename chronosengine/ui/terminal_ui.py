import curses


def draw_layout(stdscr):
    """Draw the ChronosEngine dashboard with a top-of-book display."""
    curses.curs_set(0)
    stdscr.erase()

    height, width = stdscr.getmaxyx()

    # Header
    title = " ChronosEngine - Matching Engine Dashboard "
    stdscr.addnstr(0, 0, title, max(0, width - 1))

    # Top-of-book table
    if height >= 9 and width >= 50:
        stdscr.addstr(2, 2, "TOP OF BOOK")

        stdscr.addstr(3, 2, "+" + "-" * 17 + "+" + "-" * 17 + "+")
        stdscr.addstr(4, 2, "|    BEST BID     |    BEST ASK     |")
        stdscr.addstr(5, 2, "+" + "-" * 17 + "+" + "-" * 17 + "+")
        stdscr.addstr(6, 2, "| Price: ---.--   | Price: ---.--   |")
        stdscr.addstr(7, 2, "| Size:  -----   | Size:  -----   |")
        stdscr.addstr(8, 2, "+" + "-" * 17 + "+" + "-" * 17 + "+")
    else:
        message = "Enlarge terminal to at least 50 columns and 9 rows."
        if height > 2:
            stdscr.addnstr(2, 0, message, max(0, width - 1))

    # Footer
    footer = "Press Q to quit"
    if height > 1:
        stdscr.addnstr(height - 1, 0, footer, max(0, width - 1))

    stdscr.refresh()


def main(stdscr):
    """Run the terminal window event loop."""
    while True:
        draw_layout(stdscr)
        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            break


if __name__ == "__main__":
    curses.wrapper(main)