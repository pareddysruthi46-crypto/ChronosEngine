# ChronosEngine Simulation Runbook

## 1. Purpose

This runbook describes synthetic order generation, workload configuration, memory-mapped ring-buffer storage, and producer performance verification.

The producer benchmark measures the order-generation and memory-mapped write path. It does not represent complete matching-engine throughput.

## 2. Architecture

```text
Synthetic Order Generator
          |
          v
Order Metadata and Ingress Timestamp
          |
          v
Binary Order Packing
          |
          v
MMap Ring Buffer
          |
          v
Stored Order Verification
          |
          v
Producer Performance Metrics
```

## 3. Order Schema

The current main-branch binary record contains five fields:

| Field | Description |
|---|---|
| order_id | Sequential order identifier |
| side | Buy (B) or Sell (S) |
| price | Order price |
| quantity | Order quantity |
| timestamp | Ingress timestamp in nanoseconds |

The schema is defined by `ORDER_STRUCT` in `order_schema.py`.

The binary format is:

```python
struct.Struct("<Qc7xdI4xQ")
```

The resulting record size is 40 bytes.

Order type is generated as additional metadata but is not serialized in this binary record.

Order type selection weights:

| Type | Weight |
|---|---:|
| MARKET | 20% |
| LIMIT | 60% |
| IOC | 20% |

## 4. Order Generation Parameters

The `generate_mock_orders()` function supports:

| Parameter | Default | Description |
|---|---:|---|
| count | 10 | Number of generated orders when called directly |
| rate | 100,000 | Normal target orders per second |
| news_profile | none | Normal or earnings profile |
| burst_rate | None | Target rate during a burst |
| burst_duration | 5 seconds | Burst duration |
| news_delay | 1 second | Delay before burst |

When `burst_rate` is not specified, it defaults to five times the normal rate.

## 5. Command-Line Parameters

| Argument | Default | Description |
|---|---:|---|
| `--count` | 100,000 | Total generated orders |
| `--rate` | 100,000 | Normal target orders per second |
| `--capacity` | 100 | Ring-buffer capacity |
| `--buffer` | orders_buffer.dat | Backing file |
| `--quiet` | Disabled | Suppresses individual order output |
| `--news-profile` | none | `none` or `earnings` |
| `--burst-rate` | Automatic | Custom burst target rate |
| `--burst-duration` | 5.0 | Burst duration in seconds |
| `--news-delay` | 1.0 | Delay before burst |

Validation rules:

- Order count must be zero or greater.
- Normal rate and buffer capacity must be greater than zero.
- Burst rate, when supplied, must be greater than zero.
- Burst duration must be greater than zero.
- News delay must be zero or greater.
- News profile must be `none` or `earnings`.

## 6. Running the Producer

Display command-line options:

```powershell
python mock_tick_generator.py --help
```

Run a small producer test:

```powershell
python mock_tick_generator.py --count 1000 --rate 100000 --capacity 1000 --buffer orders_test.dat --quiet
```

For complete retention, buffer capacity must be at least the number of generated orders.

Important: The default capacity of 100 does not retain all 100,000 default generated orders. Older unread records are overwritten when the ring buffer becomes full.

## 7. Workload Profiles

### 7.1 Normal workload

```powershell
python mock_tick_generator.py --count 10000 --rate 100000 --capacity 10000 --buffer normal_workload.dat --news-profile none --quiet
```

### 7.2 Earnings-news workload

```powershell
python mock_tick_generator.py --count 10000 --rate 100000 --capacity 10000 --buffer earnings_workload.dat --news-profile earnings --burst-rate 500000 --burst-duration 5 --news-delay 1 --quiet
```

The earnings profile simulates a temporary increase in order-generation rate after the configured news delay.

## 8. Batched Memory-Mapped Writes

The producer packs orders using `ORDER_STRUCT` and writes them through `push_packed()`.

The packed-write API supports:

- `flush=True`: flushes the memory map after each record.
- `flush=False`: skips the per-record flush.
- `buffer.flush()`: explicitly flushes pending memory-mapped changes.

The high-throughput producer uses `flush=False` for individual writes and calls `buffer.flush()` once after the batch.

The final flush is included in the elapsed-time measurement.

## 9. Producer Metrics

The producer reports:

- Number of generated orders.
- Elapsed time.
- Average throughput in orders per second.
- Number of orders retained in the buffer.
- Remaining unread orders.
- First and last retained orders.

Throughput is calculated as:

```text
throughput = generated_orders / elapsed_seconds
```

The producer benchmark does not measure the full matching-engine pipeline or database persistence throughput.

## 10. Performance Observations

Previously recorded local measurements:

| Batch size | Observed throughput |
|---:|---:|
| 10,000 | Approximately 48,510 orders/sec |
| 100,000 | Approximately 41,334 orders/sec |

These are historical local observations, not guaranteed targets. Hardware, operating-system scheduling, Python overhead, and buffer configuration can change the results.

## 11. Verification

Compile the relevant modules:

```powershell
python -m py_compile mmap_ringbuffer.py mock_tick_generator.py
```

Run the regression suite:

```powershell
python -m pytest test_mmap_ringbuffer_packed.py test_mmap_ringbuffer_stress.py test_mmap_trade_ringbuffer.py test_buffer_watermarks.py test_ingress_timestamp.py test_trade_consumer.py test_trade_ledger.py test_trade_ledger_indexes.py -v
```

For a complete retention test, the expected stored count is:

```text
min(generated_orders, buffer_capacity)
```

## 12. Limitations

- Producer throughput is not end-to-end matching-engine throughput.
- Small ring-buffer capacity causes older unread records to be overwritten.
- The earnings profile uses simulated news timing, not real market-news events.
- Local benchmark measurements are environment-dependent.
- A final memory-map flush is included in batch elapsed time.

## 13. Cleanup

Remove generated test buffers after verification:

```powershell
Remove-Item .\orders_test.dat, .\orders_test.dat.lock -ErrorAction SilentlyContinue
Remove-Item .\normal_workload.dat, .\normal_workload.dat.lock -ErrorAction SilentlyContinue
Remove-Item .\earnings_workload.dat, .\earnings_workload.dat.lock -ErrorAction SilentlyContinue
```

Do not remove project source files or local backups.