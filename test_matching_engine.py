
import unittest

from chronosengine.matching_engine import MatchingEngine


class TestMatchingEngine(unittest.TestCase):

    # Test 1: Partial fill
    def test_partial_fill(self):
        engine = MatchingEngine()
        engine.submit_order(1, "B", 102, 5, 1)
        result = engine.submit_order(2, "S", 101, 3, 2)

        self.assertEqual(result["filled_quantity"], 3)
        self.assertEqual(result["remaining_quantity"], 0)
        self.assertEqual(engine.get_trades()[0]["price"], 102)
        self.assertEqual(engine.get_trades()[0]["quantity"], 3)
        self.assertEqual(engine.get_order_book()["buys"][0]["quantity"], 2)

    # Test 2: Time priority
    def test_time_priority(self):
        engine = MatchingEngine()
        engine.submit_order(10, "B", 100, 5, 10)
        engine.submit_order(20, "B", 100, 4, 20)
        engine.submit_order(30, "S", 100, 6, 30)

        trades = engine.get_trades()

        self.assertEqual(trades[0]["buy_order_id"], 10)
        self.assertEqual(trades[0]["quantity"], 5)
        self.assertEqual(trades[1]["buy_order_id"], 20)
        self.assertEqual(trades[1]["quantity"], 1)

    # Test 3: Price priority
    def test_price_priority(self):
        engine = MatchingEngine()
        engine.submit_order(1, "B", 99, 2, 1)
        engine.submit_order(2, "B", 101, 3, 2)
        engine.submit_order(3, "S", 98, 4, 3)

        trades = engine.get_trades()

        self.assertEqual(trades[0]["buy_order_id"], 2)
        self.assertEqual(trades[0]["quantity"], 3)
        self.assertEqual(trades[1]["buy_order_id"], 1)
        self.assertEqual(trades[1]["quantity"], 1)

    # Test 4: Crossing buy matches resting sell
    def test_crossing_buy_matches_resting_sell(self):
        engine = MatchingEngine()
        engine.submit_order(101, "S", 100, 4, 1)

        result = engine.submit_order(102, "B", 105, 4, 2)
        trades = engine.get_trades()

        self.assertEqual(result["filled_quantity"], 4)
        self.assertEqual(result["remaining_quantity"], 0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["buy_order_id"], 102)
        self.assertEqual(trades[0]["sell_order_id"], 101)
        self.assertEqual(trades[0]["price"], 100)
        self.assertEqual(trades[0]["quantity"], 4)

    # Test 5: Crossing sell matches resting buy
    def test_crossing_sell_matches_resting_buy(self):
        engine = MatchingEngine()
        engine.submit_order(201, "B", 100, 5, 1)

        result = engine.submit_order(202, "S", 95, 3, 2)
        trades = engine.get_trades()

        self.assertEqual(result["filled_quantity"], 3)
        self.assertEqual(result["remaining_quantity"], 0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["buy_order_id"], 201)
        self.assertEqual(trades[0]["sell_order_id"], 202)
        self.assertEqual(trades[0]["price"], 100)
        self.assertEqual(trades[0]["quantity"], 3)
        self.assertEqual(engine.get_order_book()["buys"][0]["quantity"], 2)

    # Test 6: Non-crossing orders do not execute
    def test_non_crossing_orders_do_not_execute(self):
        engine = MatchingEngine()
        engine.submit_order(301, "B", 95, 5, 1)
        result = engine.submit_order(302, "S", 100, 3, 2)

        self.assertEqual(result["filled_quantity"], 0)
        self.assertEqual(result["remaining_quantity"], 3)
        self.assertEqual(len(engine.get_trades()), 0)
        self.assertEqual(len(engine.get_order_book()["buys"]), 1)
        self.assertEqual(len(engine.get_order_book()["sells"]), 1)

    # Test 7: Deterministic matching
    def test_deterministic_matching(self):
        def run_matching_scenario():
            engine = MatchingEngine()
            engine.submit_order(401, "S", 100, 2, 1)
            engine.submit_order(402, "S", 101, 3, 2)
            engine.submit_order(403, "B", 105, 4, 3)
            return engine.get_trades(), engine.get_order_book()

        first_result = run_matching_scenario()
        second_result = run_matching_scenario()

        self.assertEqual(first_result, second_result)
        self.assertEqual(len(first_result[0]), 2)
        self.assertEqual(first_result[0][0]["price"], 100)
        self.assertEqual(first_result[0][0]["quantity"], 2)
        self.assertEqual(first_result[0][1]["price"], 101)
        self.assertEqual(first_result[0][1]["quantity"], 2)
        self.assertEqual(first_result[1]["buys"], [])

    # Test 8: Direct insertion without matching
    def test_direct_insertion_without_matching(self):
        engine = MatchingEngine()

        self.assertIs(engine.insert_order(501, "S", 105, 5, 1), True)
        self.assertIs(engine.insert_order(502, "B", 95, 3, 2), True)

        book = engine.get_order_book()

        self.assertEqual(len(book["sells"]), 1)
        self.assertEqual(len(book["buys"]), 1)
        self.assertEqual(len(engine.get_trades()), 0)

    # Test 9: Cancel order at best price
    def test_cancel_order_at_best_price(self):
        engine = MatchingEngine()
        engine.insert_order(601, "S", 100, 5, 1)
        engine.insert_order(602, "S", 101, 4, 2)

        self.assertIs(engine.cancel_order(601), True)

        book = engine.get_order_book()

        self.assertEqual(len(book["sells"]), 1)
        self.assertEqual(book["sells"][0]["order_id"], 602)
        self.assertEqual(book["sells"][0]["price"], 101)

    # Test 10: Remove empty price level
    def test_remove_empty_price_level_after_cancellation(self):
        engine = MatchingEngine()
        engine.insert_order(701, "B", 100, 5, 1)
        engine.insert_order(702, "B", 99, 4, 2)

        self.assertIs(engine.cancel_order(701), True)

        book = engine.get_order_book()

        self.assertEqual(len(book["buys"]), 1)
        self.assertEqual(book["buys"][0]["order_id"], 702)
        self.assertEqual(book["buys"][0]["price"], 99)

    # Test 11: Cancel nonexistent order
    def test_cancel_nonexistent_order(self):
        engine = MatchingEngine()
        engine.insert_order(801, "B", 100, 5, 1)

        self.assertIs(engine.cancel_order(999), False)
        self.assertEqual(len(engine.get_order_book()["buys"]), 1)

    # Test 12: FIFO priority after cancellation
    def test_fifo_priority_after_cancellation(self):
        engine = MatchingEngine()
        engine.insert_order(901, "B", 100, 5, 1)
        engine.insert_order(902, "B", 100, 4, 2)
        engine.insert_order(903, "B", 100, 3, 3)

        self.assertIs(engine.cancel_order(902), True)

        engine.submit_order(904, "S", 100, 7, 4)
        trades = engine.get_trades()

        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]["buy_order_id"], 901)
        self.assertEqual(trades[0]["quantity"], 5)
        self.assertEqual(trades[1]["buy_order_id"], 903)
        self.assertEqual(trades[1]["quantity"], 2)

    # Test 13: Failed submission must not consume order ID
    def test_failed_submission_does_not_consume_order_id(self):
        engine = MatchingEngine(node_pool_size=1)

        engine.insert_order(1001, "B", 100, 10, 1)

        with self.assertRaises(MemoryError):
            engine.submit_order(1002, "B", 90, 5, 2)

        # Existing order must remain unchanged.
        book = engine.get_order_book()

        self.assertEqual(len(book["buys"]), 1)
        self.assertEqual(book["buys"][0]["order_id"], 1001)
        self.assertEqual(book["buys"][0]["quantity"], 10)

        # Release the pool node and retry the same order ID.
        self.assertIs(engine.cancel_order(1001), True)

        result = engine.submit_order(1002, "B", 90, 5, 3)

        self.assertEqual(result["filled_quantity"], 0)
        self.assertEqual(result["remaining_quantity"], 5)
        self.assertEqual(
            engine.get_memory_pool_stats(),
            {
                "capacity": 1,
                "available": 0,
                "in_use": 1,
            },
        )

        self.assertEqual(
            engine.get_order_book()["buys"][0]["order_id"],
            1002,
        )


if __name__ == "__main__":
    unittest.main()
