
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

# Test 8: Incoming order remainder persists after a partial fill.
engine = MatchingEngine()
engine.submit_order(501, "S", 100, 3, 1)

result = engine.submit_order(502, "B", 100, 5, 2)

assert result["filled_quantity"] == 3
assert result["remaining_quantity"] == 2

book = engine.get_order_book()
assert len(book["buys"]) == 1
assert book["buys"][0]["order_id"] == 502
assert book["buys"][0]["quantity"] == 2
assert book["sells"] == []

trades = engine.get_trades()
assert len(trades) == 1
assert trades[0]["quantity"] == 3

print("PASS: Incoming order remainder persists after partial fill")
