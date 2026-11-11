# ChronosEngine — Final Presentation Figures

## Included figures

- `pipeline_flow.png` — order-to-trade-to-ledger pipeline.
- `matching_throughput.png` — ten matching-engine benchmark runs.
- `matching_latency.png` — latency percentiles and maximum outlier.
- `ingestion_persistence_rate.png` — end-to-end persistence rate by batch size.
- `ingestion_queue_metrics.png` — queue drain time and maximum sampled backlog.
- `benchmark_summary.csv` — numerical data used for the graphs.
- `generate_figures.py` — reproducible chart-generation script.
- `ingestion_batch_100.txt`, `ingestion_batch_500.txt`, `ingestion_batch_1000.txt` — raw ingestion benchmark outputs.

## Matching accuracy and throughput

- 10,000 orders per measured run; 10 measured runs.
- Average throughput: 445,490 orders/sec.
- Median throughput: 461,240 orders/sec.
- Range: 346,576–530,009 orders/sec.
- 8,134 expected and actual trades per run.
- Zero trade mismatches, missing trades, unexpected trades, or remaining order-book mismatches.

## Matching latency

- 50,000 measured matching operations across five runs.
- P50: 1.2 microseconds.
- P90: 1.5 microseconds.
- P99: 3.2 microseconds.
- Maximum: 609.2 microseconds.
- 99.962% of operations were below 50 microseconds.

Important: the latency benchmark measures the Python-visible `submit_order()` call. It does not measure the complete mmap producer-to-consumer pipeline. The maximum latency exceeded 50 microseconds, so do not claim every operation met the threshold.

## Trade ingestion

Each configuration submitted 50,000 trades and persisted all 50,000, with zero missing records.

| Batch size | End-to-end persistence rate | End-to-end time | Queue drain time |
|---:|---:|---:|---:|
| 100 | 7,318 trades/sec | 6.8328 sec | 6.0389 sec |
| 500 | 21,170 trades/sec | 2.3619 sec | 1.2871 sec |
| 1,000 | 22,457 trades/sec | 2.2264 sec | 0.6753 sec |

The persistence rate is calculated as total persisted trades divided by end-to-end elapsed time. It is not a pure SQLite worker throughput measurement.

The maximum backlog is sampled by the benchmark and should not be described as an exact peak queue depth.

Batch size 1,000 was fastest in this single set of runs. More repetitions are needed before treating it as the optimal production setting.

## Pipeline interpretation

The diagram shows the asynchronous persistence path:

Order producer -> order mmap ring buffer -> order consumer/matching engine -> trade publisher -> multiprocessing queue -> batch consumer worker -> SQLite WAL trade ledger.

The persistence worker batches writes and retries failed batch inserts. SQLite is configured for WAL journal mode and synchronous FULL.

## Measurement limitations

- The matching throughput, matching latency, and ingestion measurements are separate benchmarks.
- Do not combine them into one end-to-end performance claim.
- The ingestion comparison has one run per batch-size configuration.
- Results are machine- and workload-dependent.
- Repeat the ingestion matrix several times before making production tuning decisions.

## Order book algorithm and compiled engine benchmark

See [Order Book Algorithm and Compiled Engine Benchmark](order_book_cython_benchmark.md) for the matching algorithm, Cython implementation, accuracy validation, throughput measurements, and benchmark limitations.
