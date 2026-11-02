
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
# Test 8: Direct insertion without matching.
engine = MatchingEngine()
assert engine.insert_order(501, "S", 105, 5, 1) is True
assert engine.insert_order(502, "B", 95, 3, 2) is True

book = engine.get_order_book()
assert len(book["sells"]) == 1
assert len(book["buys"]) == 1
assert len(engine.get_trades()) == 0
print("PASS: Direct insertion without matching")


# Test 9: Cancel an order at the best price.
engine = MatchingEngine()
engine.insert_order(601, "S", 100, 5, 1)
engine.insert_order(602, "S", 101, 4, 2)

assert engine.cancel_order(601) is True

book = engine.get_order_book()
assert len(book["sells"]) == 1
assert book["sells"][0]["order_id"] == 602
assert book["sells"][0]["price"] == 101
print("PASS: Cancel order at best price")


# Test 10: Cancel the final order at a price level.
engine = MatchingEngine()
engine.insert_order(701, "B", 100, 5, 1)
engine.insert_order(702, "B", 99, 4, 2)

assert engine.cancel_order(701) is True

book = engine.get_order_book()
assert len(book["buys"]) == 1
assert book["buys"][0]["order_id"] == 702
assert book["buys"][0]["price"] == 99
print("PASS: Remove empty price level after cancellation")


# Test 11: Cancelling a nonexistent order.
engine = MatchingEngine()
engine.insert_order(801, "B", 100, 5, 1)

assert engine.cancel_order(999) is False
assert len(engine.get_order_book()["buys"]) == 1
print("PASS: Nonexistent cancellation")


# Test 12: Preserve FIFO priority after cancellation.
engine = MatchingEngine()
engine.insert_order(901, "B", 100, 5, 1)
engine.insert_order(902, "B", 100, 4, 2)
engine.insert_order(903, "B", 100, 3, 3)

assert engine.cancel_order(902) is True

engine.submit_order(904, "S", 100, 7, 4)
trades = engine.get_trades()

assert len(trades) == 2
assert trades[0]["buy_order_id"] == 901
assert trades[0]["quantity"] == 5
assert trades[1]["buy_order_id"] == 903
assert trades[1]["quantity"] == 2
print("PASS: FIFO priority after cancellation")

print("All insertion and cancellation tests passed!")
