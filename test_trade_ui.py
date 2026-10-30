import curses
from chronosengine.matching_engine import MatchingEngine
from chronosengine.ui.terminal_ui import main

engine = MatchingEngine()
engine.submit_order(1, "B", 100.0, 10, 1)
engine.submit_order(2, "S", 100.0, 5, 2)

print("Prepared trades:", engine.get_trades())
curses.wrapper(lambda stdscr: main(stdscr, engine))
