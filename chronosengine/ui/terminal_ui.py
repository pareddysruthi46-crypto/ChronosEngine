
import curses


def draw_layout(stdscr):
    """Draw the initial ChronosEngine terminal dashboard."""
    curses.curs_set(0)
    stdscr.clear()

    height, width = stdscr.getmaxyx()

    # Header
    stdscr.addstr(0, 0, " ChronosEngine - Matching Engine Dashboard ".ljust(width - 1))

    # Main display grid
    if height > 4 and width > 20:
        stdscr.addstr(2, 2, "+" + "-" * (width - 6) + "+")
        stdscr.addstr(3, 2, "| Orders / Market Data".ljust(width - 3) + "|")
        stdscr.addstr(4, 2, "+" + "-" * (width - 6) + "+")

    stdscr.addstr(
        max(0, height - 2),
        2,
        "Press Q to quit | Resize terminal and restart if needed",
    )
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
