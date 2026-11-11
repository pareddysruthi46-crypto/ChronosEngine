
from chronosengine.matching_engine import MatchingEngine

# Test 1: Partial fill
engine = MatchingEngine()
engine.submit_order(1, "B", 102, 5, 1)
result = engine.submit_order(2, "S", 101, 3, 2)

assert result["filled_quantity"] == 3
assert result["remaining_quantity"] == 0
assert engine.get_trades()[0]["price"] == 102
assert engine.get_trades()[0]["quantity"] == 3
assert engine.get_order_book()["buys"][0]["quantity"] == 2
print("PASS: Partial fill")

# Test 2: Time priority
engine = MatchingEngine()
engine.submit_order(10, "B", 100, 5, 10)
engine.submit_order(20, "B", 100, 4, 20)
engine.submit_order(30, "S", 100, 6, 30)

trades = engine.get_trades()
assert trades[0]["buy_order_id"] == 10
assert trades[0]["quantity"] == 5
assert trades[1]["buy_order_id"] == 20
assert trades[1]["quantity"] == 1
print("PASS: Time priority")

# Test 3: Price priority
engine = MatchingEngine()
engine.submit_order(1, "B", 99, 2, 1)
engine.submit_order(2, "B", 101, 3, 2)
engine.submit_order(3, "S", 98, 4, 3)

trades = engine.get_trades()
assert trades[0]["buy_order_id"] == 2
assert trades[0]["quantity"] == 3
assert trades[1]["buy_order_id"] == 1
assert trades[1]["quantity"] == 1
print("PASS: Price priority")

print("All smoke tests passed!")

# Test 4: Crossing buy order matches resting sell order.
engine = MatchingEngine()
engine.submit_order(101, "S", 100, 4, 1)

result = engine.submit_order(102, "B", 105, 4, 2)
trades = engine.get_trades()

assert result["filled_quantity"] == 4
assert result["remaining_quantity"] == 0
assert len(trades) == 1
assert trades[0]["buy_order_id"] == 102
assert trades[0]["sell_order_id"] == 101
assert trades[0]["price"] == 100
assert trades[0]["quantity"] == 4
print("PASS: Crossing buy matches resting sell")


# Test 5: Crossing sell order matches resting buy order.
engine = MatchingEngine()
engine.submit_order(201, "B", 100, 5, 1)

result = engine.submit_order(202, "S", 95, 3, 2)
trades = engine.get_trades()

assert result["filled_quantity"] == 3
assert result["remaining_quantity"] == 0
assert len(trades) == 1
assert trades[0]["buy_order_id"] == 201
assert trades[0]["sell_order_id"] == 202
assert trades[0]["price"] == 100
assert trades[0]["quantity"] == 3
assert engine.get_order_book()["buys"][0]["quantity"] == 2
print("PASS: Crossing sell matches resting buy")


# Test 6: Non-crossing limit orders must not execute.
engine = MatchingEngine()
engine.submit_order(301, "B", 95, 5, 1)
result = engine.submit_order(302, "S", 100, 3, 2)

assert result["filled_quantity"] == 0
assert result["remaining_quantity"] == 3
assert len(engine.get_trades()) == 0
assert len(engine.get_order_book()["buys"]) == 1
assert len(engine.get_order_book()["sells"]) == 1
print("PASS: Non-crossing orders do not execute")


# Test 7: Matching results must be deterministic.
def run_matching_scenario():
    engine = MatchingEngine()
    engine.submit_order(401, "S", 100, 2, 1)
    engine.submit_order(402, "S", 101, 3, 2)
    engine.submit_order(403, "B", 105, 4, 3)
    return engine.get_trades(), engine.get_order_book()


first_result = run_matching_scenario()
second_result = run_matching_scenario()

assert first_result == second_result
assert len(first_result[0]) == 2
assert first_result[0][0]["price"] == 100
assert first_result[0][0]["quantity"] == 2
assert first_result[0][1]["price"] == 101
assert first_result[0][1]["quantity"] == 2
assert first_result[1]["buys"] == []
print("PASS: Matching results are deterministic")

print("All matching tests passed!")


# Test 8: Incremental trade extraction must not duplicate or miss trades.
engine = MatchingEngine()

# Create two resting sell orders at different prices.
engine.submit_order(501, "S", 100, 2, 1)
engine.submit_order(502, "S", 101, 3, 2)

# This buy order matches both resting sell orders, producing two trades.
engine.submit_order(503, "B", 105, 3, 3)

cursor = 0
first_batch = engine.get_trades_since(cursor)

assert len(first_batch) == 2
assert first_batch[0]["sell_order_id"] == 501
assert first_batch[0]["quantity"] == 2
assert first_batch[1]["sell_order_id"] == 502
assert first_batch[1]["quantity"] == 1

cursor += len(first_batch)
assert cursor == 2

# Create another trade after advancing the cursor.
engine.submit_order(504, "S", 102, 2, 4)
engine.submit_order(505, "B", 105, 2, 5)

second_batch = engine.get_trades_since(cursor)

assert len(second_batch) == 1
assert second_batch[0]["sell_order_id"] == 502
assert second_batch[0]["quantity"] == 2

cursor += len(second_batch)
assert cursor == 3

# Reading again at the current cursor must return no duplicate trades.
third_batch = engine.get_trades_since(cursor)
assert third_batch == []

# All incremental batches must exactly match the full trade history.
incremental_trades = first_batch + second_batch + third_batch
assert incremental_trades == engine.get_trades()
assert cursor == len(engine.get_trades())

print("PASS: Incremental extraction, cursor advancement, and no duplicates")


# Test 9: Invalid incremental extraction cursors must be rejected.
for invalid_cursor, expected_exception in [
    (-1, ValueError),
    (len(engine.get_trades()) + 1, ValueError),
    (True, TypeError),
    (1.5, TypeError),
]:
    try:
        engine.get_trades_since(invalid_cursor)
        raise AssertionError(
            f"Expected {expected_exception.__name__} for {invalid_cursor!r}"
        )
    except expected_exception:
        pass

print("PASS: Invalid incremental extraction cursors are rejected")
