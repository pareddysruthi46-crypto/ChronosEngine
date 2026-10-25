
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
