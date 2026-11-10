\# ChronosEngine: System Architecture and Zero-Copy IPC



\## 1. Introduction



ChronosEngine is a low-latency order-matching system designed to process incoming orders and publish matched trades efficiently. Inter-Process Communication (IPC) connects independent components of the system without requiring every message to be serialized as a Python object and transferred through a conventional queue.



The IPC implementation uses memory-mapped files (`mmap`) arranged as circular ring buffers. Fixed-size binary records represent orders and trades. Producers write records into the buffers, while consumers read and process them.



This chapter describes the system architecture, binary memory layout, producer-consumer workflow, synchronization mechanisms, zero-copy trade-buffer interface, and graceful shutdown design.



\## 2. Overall System Architecture



The system can be understood as a sequence of processing stages:



1\. An order producer creates an order.

2\. The order is encoded using the fixed-size order schema.

3\. The order is published to the memory-mapped order ring buffer.

4\. A consumer reads the order and passes it to the matching component.

5\. Matching logic processes eligible buy and sell orders.

6\. Matched executions are encoded as trade records.

7\. Trade records are published to the memory-mapped trade ring buffer.

8\. A downstream consumer reads the trades for persistence or further processing.



The order and trade ring buffers are separate IPC channels. This separation allows order submission and trade delivery to operate as distinct producer-consumer workflows.



```text

+--------------------+

|  Order Producer    |

|  Create Order      |

+---------+----------+

&#x20;         |

&#x20;         v

+--------------------+

| Order Binary Schema|

| 40-byte Record     |

+---------+----------+

&#x20;         |

&#x20;         v

+----------------------------+

| Memory-Mapped Order Buffer |

| 24-byte Header + Slots     |

+-------------+--------------+

&#x20;             |

&#x20;             v

+----------------------------+

| Order Consumer / Matching  |

| Component                  |

+-------------+--------------+

&#x20;             |

&#x20;             | Matched execution

&#x20;             v

+--------------------+

| Trade Binary Schema|

| 44-byte Record     |

+---------+----------+

&#x20;         |

&#x20;         v

+----------------------------+

| Memory-Mapped Trade Buffer |

| 24-byte Header + Slots     |

+-------------+--------------+

&#x20;             |

&#x20;             v

+----------------------------+

| Trade Consumer             |

| Persistence / Processing   |

+----------------------------+

```



\## 3. Memory-Mapped Ring Buffer Architecture



A ring buffer is a fixed-capacity storage structure in which slots are reused circularly. The buffer maintains read and write positions to identify where records should be consumed and published.



ChronosEngine backs its ring buffers with memory-mapped files. Processes map the same file into their address spaces and use the shared data region to exchange records.



The buffer layout consists of:



\- A fixed-size metadata header.

\- A sequence of fixed-size record slots.

\- A shared lock mechanism to coordinate access.



Both the order and trade ring buffers use a 24-byte header, as verified from the implementation.



The total mapped file size is determined by:



`Total size = Header size + (Capacity × Record size)`



For the current implementation:



\- Order buffer: `24 + (Capacity × 40)` bytes.

\- Trade buffer: `24 + (Capacity × 44)` bytes.



The actual total size depends on the configured capacity.



\## 4. Binary Record Layout



Fixed-size binary records provide predictable slot sizes and avoid repeatedly transferring variable-sized Python objects.



\### 4.1 Order Record



The order schema uses:



`struct.Struct("<Qc7xdI4xQ")`



The resulting record size is 40 bytes.



| Field | Data type | Offset | Size |

|---|---|---:|---:|

| Order ID | Unsigned 64-bit integer (`Q`) | 0 | 8 bytes |

| Side | Character (`c`) | 8 | 1 byte |

| Padding | Reserved bytes (`7x`) | 9 | 7 bytes |

| Price | Double (`d`) | 16 | 8 bytes |

| Quantity | Unsigned 32-bit integer (`I`) | 24 | 4 bytes |

| Padding | Reserved bytes (`4x`) | 28 | 4 bytes |

| Timestamp | Unsigned 64-bit integer (`Q`) | 32 | 8 bytes |

| \*\*Total\*\* | | | \*\*40 bytes\*\* |



The padding fields provide a defined binary layout. They are not additional business fields.



\### 4.2 Trade Record



The trade schema uses:



`struct.Struct("<QQQdIQ")`



The resulting record size is 44 bytes.



| Field | Data type | Offset | Size |

|---|---|---:|---:|

| Trade ID | Unsigned 64-bit integer (`Q`) | 0 | 8 bytes |

| Buy Order ID | Unsigned 64-bit integer (`Q`) | 8 | 8 bytes |

| Sell Order ID | Unsigned 64-bit integer (`Q`) | 16 | 8 bytes |

| Execution Price | Double (`d`) | 24 | 8 bytes |

| Quantity | Unsigned 32-bit integer (`I`) | 32 | 4 bytes |

| Timestamp | Unsigned 64-bit integer (`Q`) | 36 | 8 bytes |

| \*\*Total\*\* | | | \*\*44 bytes\*\* |



The order and trade schemas validate important input values before packing. For example, identifiers and quantities must be positive, and prices must be positive.



\## 5. Order Producer-Consumer Workflow



The order producer converts an order into its fixed-size binary representation and writes it into the order ring buffer.



The consumer reads the next available record, decodes it, and advances the read position. The implementation provides methods for writing normal order objects and already-packed records.



The `push\_packed()` method accepts a packed record and checks the input type and record size before writing it. This allows callers that already have a binary record to avoid repeating the object-to-record conversion.



The ordinary `read\_next()` method reads the record bytes from the mapped region and decodes them into a Python order representation.



The order buffer also exposes `read\_all()` for reading retained historical records. These APIs should not be described as zero-copy because they create Python-side byte or object representations.



\## 6. Trade Producer-Consumer Workflow



The matching component publishes matched executions to the trade ring buffer using `push\_trade()`.



Each trade contains:



\- A unique trade identifier.

\- The buy order identifier.

\- The sell order identifier.

\- The execution price.

\- The executed quantity.

\- A timestamp.



The trade consumer can use the normal `read\_next()` API to receive a decoded Python trade dictionary.



For consumers that can process the binary record directly, the buffer provides `read\_next\_view()` and `consume()`.



The expected view-based workflow is:



1\. Request the next unread trade using `read\_next\_view()`.

2\. Process the returned memoryview while it remains valid.

3\. Release the memoryview.

4\. Call `consume()` to advance the read position.



The consumer must release the view before consuming the record. This is important because the view references the mapped memory region.



\## 7. Zero-Copy IPC: What Is and Is Not Zero-Copy



Memory mapping does not automatically make an entire data pipeline zero-copy. The exact behavior depends on how each API exposes and processes the mapped bytes.



\### 7.1 Order Buffer



The order buffer's `read\_next()` creates a Python `bytes` object from the mapped record before decoding it.



Its `read\_next\_view()` method calls `read\_next()` and then packs the resulting order into a new record before returning a memoryview.



Therefore, this order-buffer view is a view over a newly created record, not a direct view of the original mmap slot. It must not be described as a zero-copy mmap view.



\### 7.2 Trade Buffer



The trade buffer's `read\_next\_view()` returns a memoryview over the relevant slice of the mapped file.



This avoids creating an intermediate `bytes` object merely to expose the record to the caller. It is the genuine mmap-backed zero-copy view interface in the current Python implementation.



The view is valid only while the mapped region remains available and the consumer follows the buffer's view-release and consume protocol.



\### 7.3 Scope of the Zero-Copy Claim



The accurate claim is that the trade buffer provides a zero-copy, mmap-backed record-view API.



It would be inaccurate to claim that every order operation, every trade operation, or the entire matching pipeline performs no copying. Decoding fields into Python objects or native variables may still involve data movement.



\## 8. Synchronization and Concurrency



Multiple processes or threads may attempt to access a ring buffer. Without synchronization, concurrent updates to the read and write positions could corrupt the buffer state or cause records to be read more than once.



ChronosEngine uses locking around critical ring-buffer operations.



The order ring buffer combines an in-process thread lock with a cross-process file lock. On Windows, the implementation uses `msvcrt` locking for inter-process coordination.



The trade ring buffer similarly combines thread-level and process-level synchronization. Its implementation supports platform-specific file locking.



The locks protect operations that update shared metadata and record positions. This provides coordinated access to the shared buffer.



Locking also has a performance cost. A process may need to wait when another process holds the lock. In particular, keeping a lock while doing lengthy processing can increase producer-consumer contention. Critical sections should therefore remain as short as the correctness requirements allow.



\## 9. Buffer Capacity and Backpressure



The order and trade buffers have different full-buffer policies.



The order ring buffer has logic for handling a full buffer and may overwrite the oldest unread order according to its configured behavior. This makes it important for the application to monitor buffer capacity and ensure that the consumer keeps pace with incoming orders.



The trade ring buffer rejects a new trade when it is full by raising `BufferError`. This avoids silently overwriting unread trade records.



The trade-buffer policy protects pending execution records, but it also means the producer must handle backpressure. A full trade buffer requires the consumer to make progress before more trades can be published.



These policies are not interchangeable. The application must account for the different data-loss and backpressure implications of each buffer.



\## 10. Graceful Shutdown



ChronosEngine uses a poison-pill record to communicate shutdown through the ring buffers.



A producer publishes the shutdown marker after pending records, allowing the consumer to process earlier records before observing the shutdown signal.



The shutdown procedure is designed to:



\- Prevent new records from being published after shutdown.

\- Preserve pending records ahead of the shutdown marker.

\- Avoid adding duplicate shutdown markers.

\- Wait for available capacity when necessary.

\- Report a timeout if the buffer remains full and shutdown cannot complete within the requested period.



The project also contains cross-process shutdown tests for both order and trade buffers.



The shutdown marker is a control record, not a normal business order or trade. Consumers must detect it rather than passing it into normal processing logic.



\## 11. Reliability and Operational Considerations



The IPC design provides several useful properties:



\- Fixed-size records simplify memory allocation and slot addressing.

\- Memory-mapped files allow independent processes to access a common data region.

\- Shared locking coordinates concurrent access.

\- Ring-buffer indices support circular reuse of storage.

\- The trade view API reduces intermediate copying when consumers can process mapped records directly.

\- Poison-pill shutdown markers provide an orderly termination mechanism.



The design also has limitations:



\- Lock acquisition can introduce contention.

\- A slow consumer can cause buffer pressure.

\- The order and trade buffers have different full-buffer policies.

\- Memoryview users must follow the required release and consume sequence.

\- Memory mapping alone does not guarantee end-to-end zero-copy behavior.

\- The system must handle process termination and resource cleanup carefully.



\## 12. Testing and Validation



The repository includes tests for the principal IPC behaviors.



| Test area | Purpose |

|---|---|

| Order packed-record tests | Validate packed writes, memoryview input, record-size checks, and shutdown rejection |

| Multi-threaded ring-buffer stress test | Exercise concurrent producers and consumers |

| Trade ring-buffer tests | Validate trade publication, reading, wraparound, capacity handling, and view-based access |

| Shutdown tests | Validate poison-pill handling and preservation of pending records |

| Cross-process shutdown tests | Validate shutdown signaling between separate processes |



These tests provide coverage for the core buffer operations and important concurrency and shutdown scenarios.



Test coverage should not be confused with a performance guarantee. Throughput and latency depend on the workload, buffer capacity, process scheduling, lock contention, and the consumer's processing time. Performance claims should be supported by benchmark results from the relevant environment.



\## 13. Conclusion



ChronosEngine uses memory-mapped circular ring buffers to exchange fixed-size order and trade records between independent components.



The 40-byte order record and 44-byte trade record provide predictable binary layouts, while the 24-byte headers maintain buffer metadata. Shared locking coordinates concurrent access, and poison-pill records support graceful shutdown.



The trade ring buffer exposes a genuine mmap-backed memoryview interface, reducing intermediate copying for consumers that can work directly with binary records. The order buffer's current view method, however, returns a view of a copied record. This distinction is essential when describing the system's zero-copy capabilities.



Overall, the architecture provides a structured IPC foundation for low-latency order and trade processing while making its synchronization, capacity, and data-access trade-offs explicit.

