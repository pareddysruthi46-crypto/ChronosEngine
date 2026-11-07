import pytest

from chronosengine.matching_engine import MatchingEngine
from whale_order_injector import inject_whale_order


def test_whale_buy_clears_multiple_sell_levels():
    engine = MatchingEngine()

    # Seed four sell-side liquidity levels.
    engine.submit_order(1001, "S", 101.0, 100, 1)
    engine.submit_order(1002, "S", 102.0, 100, 2)
    engine.submit_order(1003, "S", 103.0, 100, 3)
    engine.submit_order(1004, "S", 104.0, 100, 4)

    # Inject one large marketable Whale buy order.
    report = inject_whale_order(
        engine=engine,
        order_id=9001,
        side="B",
        price=104.0,
        quantity=350,
        timestamp=10,
    )

    assert report["filled_quantity"] == 350
    assert report["remaining_quantity"] == 0
    assert report["executed_quantity"] == 350

    assert report["levels_hit"] == 4
    assert report["matched_price_levels"] == [
        101.0, 102.0, 103.0, 104.0
    ]

    assert [
        trade["quantity"] for trade in report["trades"]
    ] == [100, 100, 100, 50]

    # Three levels are fully consumed.
    # The fourth level retains 50 units.
    remaining_sells = engine.get_order_book()["sells"]

    assert len(remaining_sells) == 1
    assert remaining_sells[0]["price"] == 104.0
    assert remaining_sells[0]["quantity"] == 50


def test_whale_sell_clears_multiple_buy_levels():
    engine = MatchingEngine()

    # Seed four buy-side liquidity levels.
    engine.submit_order(2001, "B", 104.0, 100, 1)
    engine.submit_order(2002, "B", 103.0, 100, 2)
    engine.submit_order(2003, "B", 102.0, 100, 3)
    engine.submit_order(2004, "B", 101.0, 100, 4)

    # Inject one large marketable Whale sell order.
    report = inject_whale_order(
        engine=engine,
        order_id=9002,
        side="S",
        price=101.0,
        quantity=250,
        timestamp=10,
    )

    assert report["filled_quantity"] == 250
    assert report["remaining_quantity"] == 0
    assert report["executed_quantity"] == 250

    assert report["levels_hit"] == 3
    assert report["matched_price_levels"] == [
        102.0, 103.0, 104.0
    ]

    assert [
        trade["quantity"] for trade in report["trades"]
    ] == [100, 100, 50]

    remaining_buys = engine.get_order_book()["buys"]

    assert len(remaining_buys) == 2
    assert remaining_buys[0]["price"] == 102.0
    assert remaining_buys[0]["quantity"] == 50
    assert remaining_buys[1]["price"] == 101.0
    assert remaining_buys[1]["quantity"] == 100


def test_whale_injection_rejects_invalid_side():
    engine = MatchingEngine()

    with pytest.raises(ValueError):
        inject_whale_order(
            engine, 9003, "X", 100.0, 500, 10
        )
