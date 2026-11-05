
import gc
import tracemalloc
import unittest

from chronosengine.matching_engine import MatchingEngine
from test_match_accuracy_stress import (
    build_workload,
    calculate_expected_result,
    TOTAL_ORDERS,
)


class TestMatchingEngineGCStress(unittest.TestCase):

    def test_continuous_matching_without_gc_collections(self):
        # Warm up the engine while automatic GC is enabled.
        warmup_engine = MatchingEngine(node_pool_size=1000)

        for order_id in range(1, 101):
            warmup_engine.submit_order(
                order_id, "S", 100.0, 1, order_id
            )

        for order_id in range(101, 201):
            warmup_engine.submit_order(
                order_id, "B", 110.0, 1, order_id
            )

        del warmup_engine
        gc.collect()

        # Build workload and calculate expected results before tracking.
        orders = build_workload()

        self.assertEqual(len(orders), TOTAL_ORDERS)

        expected_trades, expected_book = calculate_expected_result(
            orders
        )

        # Start Python allocation tracking after warm-up.
        tracemalloc.start()

        try:
            engine = MatchingEngine(node_pool_size=TOTAL_ORDERS)

            gc_stats_before = gc.get_stats()
            collections_before = sum(
                generation["collections"]
                for generation in gc_stats_before
            )

            memory_before, _ = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()

            gc_was_enabled = gc.isenabled()

            try:
                # Disable automatic garbage collection for stress phase.
                gc.disable()

                self.assertFalse(
                    gc.isenabled(),
                    "Automatic GC should be disabled during stress testing.",
                )

                # Submit all 10,000 orders.
                for order in orders:
                    engine.submit_order(
                        order["order_id"],
                        order["side"],
                        order["price"],
                        order["quantity"],
                        order["timestamp"],
                    )

                # Capture native pool statistics.
                pool_stats = engine.get_memory_pool_stats()

                # Capture Python-traced memory.
                memory_during, peak_memory = (
                    tracemalloc.get_traced_memory()
                )

                # Check GC collection counts during the disabled phase.
                gc_stats_after = gc.get_stats()
                collections_after = sum(
                    generation["collections"]
                    for generation in gc_stats_after
                )

            finally:
                # Restore the original GC state even if submission fails.
                if gc_was_enabled:
                    gc.enable()
                else:
                    gc.disable()

            self.assertEqual(
                collections_after,
                collections_before,
                "GC collection count changed while automatic GC was disabled.",
            )

            self.assertEqual(
                pool_stats["capacity"],
                TOTAL_ORDERS,
            )

            self.assertEqual(
                pool_stats["available"] + pool_stats["in_use"],
                pool_stats["capacity"],
            )

            # Every resting order must own one native pool node.
            order_book = engine.get_order_book()

            open_order_count = (
                len(order_book["buys"])
                + len(order_book["sells"])
            )

            self.assertEqual(
                pool_stats["in_use"],
                open_order_count,
                "Native pool usage does not match the resting order count.",
            )

            # Compare actual matching results with the independent model.
            actual_trades = engine.get_trades()

            self.assertEqual(
                actual_trades,
                expected_trades,
                "Stress-test trades differ from the independent reference model.",
            )

            self.assertEqual(
                order_book,
                expected_book,
                "Stress-test order book differs from the independent reference model.",
            )

            self.assertTrue(
                gc.isenabled() == gc_was_enabled,
                "Automatic GC state was not restored after the test.",
            )

            print("\nGC STRESS TEST RESULTS")
            print("=" * 45)
            print(f"Orders submitted: {TOTAL_ORDERS:,}")
            print(f"Trades generated: {len(actual_trades):,}")
            print(f"Open orders: {open_order_count:,}")
            print(f"Native pool capacity: {pool_stats['capacity']:,}")
            print(f"Native nodes in use: {pool_stats['in_use']:,}")
            print(f"Native nodes available: {pool_stats['available']:,}")
            print(f"GC collections before: {collections_before}")
            print(f"GC collections after: {collections_after}")
            print(f"Python memory before: {memory_before:,} bytes")
            print(f"Python memory during: {memory_during:,} bytes")
            print(f"Python peak memory: {peak_memory:,} bytes")
            print("GC collections during disabled phase: 0")
            print("Native pool consistency: PASS")
            print("Independent matching accuracy: PASS")
            print("Automatic GC state restored: PASS")

        finally:
            # Stop tracing even if an assertion or submission fails.
            if tracemalloc.is_tracing():
                tracemalloc.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
