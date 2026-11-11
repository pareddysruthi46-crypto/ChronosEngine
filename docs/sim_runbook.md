# ChronosEngine Firehose Producer Configuration and Runbook



## 1. Introduction



ChronosEngine uses an asynchronous mock tick generator to produce simulated market orders and write them into a memory-mapped circular ring buffer.



The firehose producer supports configurable workload generation, normal-rate testing, optional earnings-news bursts, binary packet creation, and ingress timestamp capture.



The main components are:



- `mock_tick_generator.py`: Generates mock orders and writes binary packets.

- `mmap_ringbuffer.py`: Provides the memory-mapped circular buffer.

- `order_schema.py`: Defines the binary order record format.

- `test_async_stress.py`: Performs a high-volume buffer-write stress test.

- `test_ingress_timestamp.py`: Validates ingress timestamp generation.



## 2. Firehose Producer Architecture



The producer follows this workflow:



```text

&#x20;      Configuration

&#x20;            |

&#x20;            v

&#x20;   Async Order Generator

&#x20;            |

&#x20;            v

&#x20;      Generate Order

&#x20;            |

&#x20;            v

&#x20;   Capture Ingress Time

&#x20;      (time.time_ns)

&#x20;            |

&#x20;            v

&#x20;     Binary Packet Packing

&#x20;       (pack_into)

&#x20;            |

&#x20;            v

&#x20;    MMap Ring Buffer

&#x20;      (push_packed)

&#x20;            |

&#x20;            v

&#x20;      Stored Orders

&#x20;            |

&#x20;            v

&#x20;    Verification and Metrics

```



The generator uses `asyncio` to schedule order generation according to the configured target rate.



## 3. Workload Generation Parameters



The `generate_mock_orders()` function supports the following parameters:



| Parameter | Default | Description |

|---|---:|---|

| `count` | 10 (function) | Number of orders to generate |

| `rate` | 100,000 | Normal target orders per second |

| `news_profile` | `none` | Workload profile: `none` or `earnings` |

| `burst_rate` | `None` | Target rate during a burst |

| `burst_duration` | 5.0 seconds | Duration of the earnings burst |

| `news_delay` | 1.0 second | Delay before the burst starts |



When `burst_rate` is not specified, it defaults to five times the normal rate.



### 3.1 Command-Line Parameters



The `mock_tick_generator.py` command-line interface supports:



| Argument | Default | Description |

|---|---:|---|

| `--count` | 100,000 | Total number of orders |

| `--rate` | 100,000 | Normal target orders per second |

| `--capacity` | 100 | Ring-buffer capacity |

| `--buffer` | `orders_buffer.dat` | Backing file name |

| `--quiet` | Disabled | Suppresses individual order output |

| `--news-profile` | `none` | Selects `none` or `earnings` |

| `--burst-rate` | Automatic | Custom burst target rate |

| `--burst-duration` | 5.0 | Burst duration in seconds |

| `--news-delay` | 1.0 | Delay before the burst |



### 3.2 Parameter Validation



The producer validates its configuration:



- Order count must be zero or greater.

- Normal rate must be greater than zero.

- Buffer capacity must be greater than zero.

- Burst rate must be greater than zero when supplied.

- Burst duration must be greater than zero.

- News delay must be zero or greater.

- News profile must be `none` or `earnings`.



Invalid command-line values are rejected through `argparse`.



## 4. Order Generation Profile



Each generated order contains:



- Order ID

- Side: Buy (`B`) or Sell (`S`)

- Price

- Quantity

- Timestamp

- Order type



The generated values use the following rules:



| Field | Generation rule |

|---|---|

| Order ID | Sequential, starting from 1 |

| Side | Randomly selected between B and S |

| Price | Random value between 100 and 250, rounded to 2 decimals |

| Quantity | Random integer between 1 and 1000 |

| Order type | MARKET, LIMIT or IOC |



Order-type selection uses these weights:



| Order type | Weight |

|---|---:|

| MARKET | 20% |

| LIMIT | 60% |

| IOC | 20% |



The binary order-type codes are:



- MARKET: `M`

- LIMIT: `L`

- IOC: `I`



## 5. Test Profiles



### 5.1 Normal Workload Profile



The normal profile uses:



```text

news_profile = none

rate = 100000

```



It generates orders at the configured normal target rate without an earnings-news burst.



### 5.2 Earnings-News Burst Profile



The earnings profile simulates increased market activity after an earnings announcement.



Default configuration:



```text

news_profile = earnings

news_delay = 1.0

burst_duration = 5.0

burst_rate = 5 \* normal_rate

```



When the news delay is reached, the producer prints an earnings announcement and activates the burst rate for the configured duration.



The burst only occurs if order generation continues long enough to reach the news delay.



### 5.3 High-Volume Stress Profile



The stress test in `test_async_stress.py` uses:



| Parameter | Value |

|---|---:|

| Total orders | 500,000 |

| Target throughput | 100,000 orders/sec |

| Buffer capacity | 500,000 |

| Buffer file | `async_stress_test.dat` |



It writes pre-packed binary records into the ring buffer, flushes the mapped file after the batch, reads the records, and checks for missing or duplicate order IDs.



The test passes when:



- All 500,000 records are received.

- No order IDs are missing.

- No duplicate order IDs exist.

- Measured throughput is at least 100,000 orders/sec.



\*\*Benchmark limitation:\*\* This test directly writes records synchronously using `_write_record()`. It measures buffer-write performance and is not a concurrent asynchronous producer-consumer benchmark.



## 6. Ingress Timestamp Handling



The producer captures the ingress timestamp using:



```python

ingress_timestamp_ns = time.time_ns()

```



Timestamp capture happens immediately before binary packet creation.



The reusable payload is packed using:



```python

ORDER_STRUCT.pack_into(

&#x20;   payload,

&#x20;   0,

&#x20;   order\["order_id"],

&#x20;   order\["side"].encode("ascii"),

&#x20;   order\["price"],

&#x20;   order\["quantity"],

&#x20;   ingress_timestamp_ns,

&#x20;   ORDER_TYPE_CODES\[order\["order_type"]],

)

```



The packed payload is then written through:



```python

buffer.push_packed(payload)

```



The timestamp is represented in epoch nanoseconds.



The ingress timestamp test checks that:



- Ten orders are generated.

- Ten orders are received.

- Every timestamp is greater than zero.

- Timestamps are non-decreasing.

- Timestamps are in the expected nanosecond scale.



## 7. Execution Runbook



Run the following commands from the ChronosEngine project root.



### 7.1 Generate a Small Normal Workload



```powershell

python mock_tick_generator.py --count 100 --rate 100000 --capacity 100 --quiet

```



### 7.2 Generate a Larger Normal Workload



```powershell

python mock_tick_generator.py --count 100000 --rate 100000 --capacity 100000 --quiet

```



### 7.3 Run the Earnings-News Profile



```powershell

python mock_tick_generator.py --count 100000 --rate 100000 --capacity 100000 --news-profile earnings --quiet

```



### 7.4 Customize the Burst



```powershell

python mock_tick_generator.py --count 100000 --rate 100000 --capacity 100000 --news-profile earnings --burst-rate 500000 --burst-duration 5 --news-delay 1 --quiet

```



### 7.5 Run the Stress Test



```powershell

python test_async_stress.py

```



### 7.6 Run the Ingress Timestamp Test



```powershell

python -m unittest -v test_ingress_timestamp

```



## 8. Result Verification



The producer reports:



- Number of generated orders.

- Elapsed execution time.

- Average throughput.

- Number of orders stored in the buffer.

- Number of unread orders.

- First and last stored orders.

- Buffer verification status.



The throughput is calculated as:



```text

Average Throughput = Generated Orders / Elapsed Time

```



The normal producer verifies that the number of stored records equals:



```text

min(generated_orders, buffer_capacity)

```



This is important because the ring buffer retains only its configured capacity and may overwrite older records.



The stress test additionally reports missing and duplicate order counts.



## 9. Operational Considerations



1\. Select buffer capacity according to the expected number of retained orders.

2\. Use `--quiet` for larger workloads to avoid individual order printing overhead.

3\. Use the normal profile for baseline workload generation.

4\. Use the earnings profile to simulate temporary increases in market activity.

5\. Compare measured throughput with the configured target rather than assuming the target rate was achieved.

6\. Use the timestamp test to validate ingress timestamp behavior.

7\. Use sufficiently large buffer capacity when testing record retention.



### Important Limitations



- The configured rate is a target, not a guaranteed achieved throughput.

- Python scheduling and system performance can affect actual generation rate.

- A small ring-buffer capacity can overwrite older unread orders.

- The stress test is a synchronous buffer-write benchmark.

- The producer's earnings burst is time-based and may not activate if generation finishes before the configured delay.

- Benchmark results depend on the execution environment.



## 10. Conclusion



The ChronosEngine firehose producer provides configurable mock market-order generation using an asynchronous scheduling mechanism and a memory-mapped ring buffer.



It supports normal workloads, earnings-news burst simulation, configurable order rates, binary packet creation, and nanosecond ingress timestamps.



The included stress and timestamp tests provide ways to evaluate buffer-write throughput, record integrity, and timestamp correctness.



## 11. Binary Order Record Layout

The producer uses `ORDER_STRUCT = struct.Struct("<Qc7xdI4xQ")` to pack each order into a fixed-size binary record.

The record contains five serialized fields. The order type is generated as additional metadata but is not serialized.

| Field | Format | Size | Byte Offset |
|---|---|---:|---:|
| Order ID | Q | 8 bytes | 0 |
| Side | c | 1 byte | 8 |
| Padding | 7x | 7 bytes | 9-15 |
| Price | d | 8 bytes | 16 |
| Quantity | I | 4 bytes | 24 |
| Padding | 4x | 4 bytes | 28-31 |
| Timestamp | Q | 8 bytes | 32 |
| Total | | 40 bytes | |

The format uses little-endian byte order. The timestamp represents ingress time in nanoseconds. Padding bytes are reserved for binary alignment and are not additional fields.