from chronosengine.matching_engine import MatchingEngine


def test_buy_order_sweeps_multiple_sell_levels():
    engine = MatchingEngine()

    engine.submit_order(1, "S", 101.0, 2, 1)
    engine.submit_order(2, "S", 102.0, 3, 2)
    engine.submit_order(3, "S", 103.0, 4, 3)

    engine.submit_order(10, "B", 105.0, 5, 4)

    events = engine.get_sweep_events()

    assert len(events) == 1
    assert events[0]["order_id"] == 10
    assert events[0]["side"] == "BUY"
    assert events[0]["levels_swept"] == 2
    assert events[0]["executed_quantity"] == 5
    assert events[0]["matched_price_levels"] == [101.0, 102.0]


def test_sell_order_sweeps_multiple_buy_levels():
    engine = MatchingEngine()

    engine.submit_order(1, "B", 103.0, 2, 1)
    engine.submit_order(2, "B", 102.0, 3, 2)
    engine.submit_order(3, "B", 101.0, 4, 3)

    engine.submit_order(10, "S", 99.0, 5, 4)

    events = engine.get_sweep_events()

    assert len(events) == 1
    assert events[0]["order_id"] == 10
    assert events[0]["side"] == "SELL"
    assert events[0]["levels_swept"] == 2
    assert events[0]["executed_quantity"] == 5
    assert events[0]["matched_price_levels"] == [103.0, 102.0]


def test_multiple_makers_at_same_price_are_one_level():
    engine = MatchingEngine()

    engine.submit_order(1, "S", 101.0, 2, 1)
    engine.submit_order(2, "S", 101.0, 3, 2)

    engine.submit_order(10, "B", 105.0, 5, 3)

    assert engine.get_sweep_events() == []


def test_non_crossing_order_does_not_create_sweep():
    engine = MatchingEngine()

    engine.submit_order(1, "S", 105.0, 5, 1)
    engine.submit_order(10, "B", 100.0, 5, 2)

    assert engine.get_sweep_events() == []


def test_single_level_execution_does_not_create_sweep():
    engine = MatchingEngine()

    engine.submit_order(1, "S", 101.0, 2, 1)
    engine.submit_order(10, "B", 105.0, 5, 2)

    assert engine.get_sweep_events() == []
