from chronosengine.matching_engine import MatchingEngine


def test_empty_order_book():
    engine = MatchingEngine()
    book = engine.get_order_book()

    assert book["buys"] == []
    assert book["sells"] == []
    assert book["best_bid"] is None
    assert book["best_ask"] is None
    assert book["spread"] is None
    assert book["is_crossed"] is False


def test_only_bid_side():
    engine = MatchingEngine()
    engine.insert_order(1, "B", 100, 5, 1)

    book = engine.get_order_book()

    assert book["best_bid"] == 100
    assert book["best_ask"] is None
    assert book["spread"] is None
    assert book["is_crossed"] is False


def test_only_ask_side():
    engine = MatchingEngine()
    engine.insert_order(1, "S", 105, 5, 1)

    book = engine.get_order_book()

    assert book["best_bid"] is None
    assert book["best_ask"] == 105
    assert book["spread"] is None
    assert book["is_crossed"] is False


def test_normal_spread():
    engine = MatchingEngine()
    engine.insert_order(1, "B", 100, 5, 1)
    engine.insert_order(2, "S", 105, 5, 2)

    book = engine.get_order_book()

    assert book["best_bid"] == 100
    assert book["best_ask"] == 105
    assert book["spread"] == 5
    assert book["is_crossed"] is False


def test_locked_book():
    engine = MatchingEngine()
    engine.insert_order(1, "B", 100, 5, 1)
    engine.insert_order(2, "S", 100, 5, 2)

    book = engine.get_order_book()

    assert book["spread"] == 0
    assert book["is_crossed"] is True


def test_crossed_book():
    engine = MatchingEngine()
    engine.insert_order(1, "B", 105, 5, 1)
    engine.insert_order(2, "S", 100, 5, 2)

    book = engine.get_order_book()

    assert book["best_bid"] == 105
    assert book["best_ask"] == 100
    assert book["spread"] == -5
    assert book["is_crossed"] is True
