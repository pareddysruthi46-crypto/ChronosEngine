# Order Book Algorithm and Compiled Engine Benchmark

## 1. Overview

ChronosEngine implements a limit order book using price-time priority. The matching engine is implemented in Cython and compiled as a native extension.

The engine maintains separate buy and sell sides, matches incoming orders against the best available opposite-side price, and preserves unmatched quantities in the order book.

The implementation and benchmark evidence described here come from the `feature/cython-engine` branch, particularly its matching engine, stress tests, and accuracy report.

## 2. Order Book Data Structures

The matching engine uses the following structures:

| Structure | Purpose |
|---|---|
| `_buys` | Buy-side price levels |
| `_sells` | Sell-side price levels |
| `PriceLevelQueue` | Doubly linked queue of orders at one price |
| `OrderNodePool` | Fixed-capacity pool of reusable native order nodes |
| `_active_orders` | Maps order IDs to their side and price |
| `_seen_order_ids` | Tracks previously submitted order IDs |
| `_trades` | Stores generated trade records |

Each price level has a linked queue with a head and tail. Orders at the same price are maintained in timestamp order. Equal timestamps retain insertion order.

The default node-pool capacity is 100,000 nodes. A pool can also be configured with a different capacity when constructing the engine.

## 3. Price-Time Priority Matching Algorithm

The engine follows two priorities:

1. **Price priority:** The best available price is matched first.
2. **Time priority:** At the same price, the earliest resting order is matched first.

### Incoming buy order

- Find the lowest-priced sell level.
- If the incoming buy price is lower than the best sell price, matching stops.
- Otherwise, match against the head of that sell queue.
- Continue until the incoming quantity is filled or no eligible sell order remains.

### Incoming sell order

- Find the highest-priced buy level.
- If the incoming sell price is higher than the best buy price, matching stops.
- Otherwise, match against the head of that buy queue.
- Continue until the incoming quantity is filled or no eligible buy order remains.

### Trade execution and partial fills

The execution price is the resting maker order's price.

For each match:

- The trade quantity is the smaller of the incoming remaining quantity and the resting order's remaining quantity.
- Both quantities are updated.
- A fully filled resting order is removed from its queue and active-order index.
- A partially filled resting order remains in the queue.
- Any unfilled incoming quantity is inserted into its own side of the book.

The native `_apply_fill` helper performs the quantity calculation and update.

### Simplified matching flow

```text
              Incoming Order
                     |
              Validate Order
                     |
              Select Opposite Side
                     |
             Find Best Price Level
                     |
             Is Price Crossable?
                /          \
              No            Yes
              |              |
        Rest Remaining    Select Queue Head
        Quantity              |
                         Calculate Fill
                              |
                       Update Quantities
                              |
                    Maker Fully Filled?
                       /          \
                     Yes           No
                      |             |
                 Remove Maker   Keep Maker
                       \          /
                        Continue
                            |
                   Incoming Remaining?
                      /          \
                    Yes           No
                     |             |
                Rest in Book    Complete
```

## 4. Cancellation and Memory Management

### Active-order index

The `_active_orders` dictionary maps an order ID to its side and price. Cancellation first uses this index to locate the relevant price-level queue rather than searching every price level.

The queue's `remove_order()` operation still searches within that linked queue. Therefore, the index reduces the search scope but does not make every cancellation constant-time.

An inconsistency between the active-order index and the order book raises a runtime error.

### Pre-allocated native node pool

`OrderNodePool` allocates a fixed-capacity block of native order nodes and maintains a free list.

- New resting orders acquire reusable nodes.
- Fully filled or cancelled orders release their nodes.
- Released nodes can be reused by subsequent orders.
- Pool exhaustion raises a `MemoryError`.

This reduces repeated native node allocation during order-book operations. It does not eliminate all Python object allocation.

## 5. Cython Compilation and Runtime Optimizations

The compiled implementation includes:

- C-level `Order` and `OrderNode` structures.
- Native pointers for linked order nodes.
- Typed numeric variables for prices, quantities, IDs, and timestamps.
- A reusable native node pool.
- A price-level queue for each active price.
- Direct reading of mapped order-buffer memory through a typed memoryview in `consume_mmap()`.
- An optional outbound matched-trade ring buffer with a validated 44-byte trade record format.

The `_apply_fill` helper is declared `noexcept nogil` and invoked inside a `with nogil` block. Python dictionary and object operations surrounding the matching process still require the Python runtime and GIL. Therefore, this should not be described as an entirely GIL-free matching engine.

### Build the extension

The repository uses `setup.py` and Cython to compile `matching_engine.pyx` as a C++ extension.

```powershell
python -m pip install --upgrade Cython setuptools wheel
python setup.py build_ext --inplace
```

A compatible C++ compiler is also required. The setup configuration uses `/O2` on Windows and `-O3` on other supported platforms.

## 6. Matching Accuracy and Stress Benchmark

The benchmark report `reports/match_accuracy_stress_report.txt` was generated on 2026-11-02.

### Workload

| Parameter | Configuration |
|---|---:|
| Resting sell orders | 5,000 |
| Aggressive buy orders | 5,000 |
| Total orders per run | 10,000 |
| Warm-up runs | 2 |
| Measured runs | 10 |
| Sell price levels | 5 |

The same deterministic workload is used for each run.

An independent Python reference model calculates expected trades and remaining orders. It applies lowest-sell-price-first matching and timestamp priority within each price level.

### Accuracy results

| Validation | Result |
|---|---:|
| Expected trades | 8,134 |
| Actual trades per run | 8,134 |
| Total traded quantity | 24,990 |
| Trade field mismatches | 0 |
| Missing trades | 0 |
| Unexpected trades | 0 |
| Remaining order-book mismatches | 0 |
| Deterministic repeated runs | PASS |

All ten measured runs matched the independent reference model.

## 7. Compiled Engine Throughput Results

The benchmark imports `MatchingEngine` from `chronosengine.matching_engine`, the compiled Cython extension.

The timer starts immediately before the 10,000-order `submit_order()` loop and stops immediately after it. Engine construction, trade extraction, and correctness validation are outside the timed interval.

### Measured runs

| Run | Throughput (orders/sec) |
|---:|---:|
| 1 | 758,708 |
| 2 | 992,812 |
| 3 | 870,148 |
| 4 | 805,095 |
| 5 | 763,685 |
| 6 | 713,190 |
| 7 | 838,863 |
| 8 | 665,256 |
| 9 | 593,218 |
| 10 | 672,106 |

### Summary

| Metric | Result |
|---|---:|
| Average execution time | 0.013297 sec |
| Average throughput | 752,048 orders/sec |
| Median execution time | 0.013137 sec |
| Median throughput | 761,189 orders/sec |
| Minimum throughput | 593,218 orders/sec |
| Maximum throughput | 992,812 orders/sec |

The throughput summary is calculated from the measured execution times. Median throughput is the total order count divided by median execution time.

These are results from the reported workload and machine. They should not be treated as a universal production throughput guarantee.

## 8. Garbage Collection Stress Validation

`test_matching_engine_gc_stress.py` checks continuous matching with automatic Python garbage collection disabled during the measured stress phase.

The test:

1. Warms up the engine while automatic GC is enabled.
2. Builds the deterministic 10,000-order workload.
3. Creates an engine with a 10,000-node pool.
4. Records GC collection counts and memory measurements.
5. Disables automatic GC and submits all 10,000 orders.
6. Confirms the collection count did not increase during the disabled phase.
7. Restores the original GC state.
8. Checks pool consistency and compares trades and the remaining book against the independent reference model.

The test reports zero automatic GC collections during the disabled phase and validates matching accuracy and native pool consistency.

This result does not mean that Python allocated zero objects. It means no automatic garbage-collection cycle occurred during that specific disabled-GC test phase.

## 9. Benchmark Scope and Limitations

- The matching accuracy and throughput figures describe the compiled-engine stress benchmark.
- The benchmark measures the Python-visible `submit_order()` loop, not complete producer-to-consumer pipeline latency.
- It excludes engine construction, result extraction, and validation from the timed interval.
- The GC stress test is a separate validation, not a throughput benchmark.
- The existing `reports/presentation/README.md` contains a separate matching benchmark with an average of 445,490 orders/sec. Its results must not be compared directly with the 752,048 orders/sec Cython report without confirming identical source revisions, hardware, workloads, and timing methodology.
- Results depend on hardware, compiler, Python/Cython versions, and workload characteristics.
- Further repeated tests on the same machine and under identical conditions are required for a reliable before-and-after optimization comparison.

## 10. Reproducing the Benchmark

After building the Cython extension and installing the required test dependencies, run:

```powershell
python test_match_accuracy_stress.py
python -m unittest test_matching_engine_gc_stress
```

The first command generates the matching accuracy and throughput report. The second runs the garbage-collection stress validation.

---

**Conclusion:** ChronosEngine combines price-time priority matching, linked price-level queues, reusable native order nodes, indexed cancellation, and Cython-compiled execution. The recorded stress benchmark processed 10,000 orders per run at an average reported throughput of 752,048 orders/sec while matching the independent reference model with zero reported trade or remaining-book mismatches.