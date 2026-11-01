\# ChronosEngine IPC Architecture and Memory Layout



\## 1. Introduction



ChronosEngine uses Inter-Process Communication (IPC) to transfer binary order data between independent processes.



The IPC mechanism is implemented using a memory-mapped file (`mmap`) organized as a circular ring buffer.



Instead of exchanging complex Python objects between processes, orders are converted into a fixed-size binary representation. This reduces serialization overhead and allows efficient access to shared memory.



The main components are:



\- Order Schema: Defines the binary format of an order.

\- Memory-Mapped Ring Buffer: Stores orders in a shared memory region backed by a file.

\- Producer: Encodes and writes orders into the ring buffer.

\- Consumer: Reads orders from the ring buffer and processes them.

\- Synchronization: Uses a shared lock file to coordinate access between processes.



\## 2. IPC Architecture



The IPC architecture follows a producer-consumer model.



```text

+----------------------+

|   Producer Process   |

|                      |

|   Create Order       |

|   pack\_order()       |

+----------+-----------+

&#x20;          |

&#x20;          v

+----------------------+

|   MMap Ring Buffer   |

|                      |

|   Shared Memory File |

|                      |

|   +----------------+ |

|   | Header (24 B)  | |

|   +----------------+ |

|   | Order Slot  0  | |

|   | Order Slot  1  | |

|   | Order Slot  2  | |

|   |      ...       | |

|   +----------------+ |

+----------+-----------+

&#x20;          |

&#x20;          v

+----------------------+

|   Consumer Process   |

|                      |

|   Read Binary Order  |

|   Decode Order       |

|   Matching Engine    |

+----------------------+



&#x20;  Shared Lock File

&#x20;  Synchronizes Access

&#x20;  Between Processes

```



\### Architecture Workflow



1\. The producer creates an order containing order ID, side, price, quantity, and timestamp.

2\. The `pack\_order()` function converts the order into binary data.

3\. The producer writes the binary record into the next available ring-buffer slot.

4\. The buffer header is updated with the write position, item count, read position, unread count, and sequence number.

5\. The consumer acquires the shared lock before accessing the buffer.

6\. The consumer reads an available order.

7\. After successful processing, the read position and unread count are updated.

8\. The lock is released so another process can access the buffer.



\## 3. Memory-Mapped File Structure



The ring buffer uses a memory-mapped file to provide shared access to the same file-backed memory region.



The total file size is calculated as:



```text

Total File Size = Header Size + (Capacity × Record Size)

```



For example, with a capacity of 100 orders:



```text

Header Size  = 24 bytes

Record Size  = 29 bytes

Capacity     = 100



Total Size = 24 + (100 × 29)

&#x20;          = 2924 bytes

```



The memory layout is:



| Region | Size |

|---|---:|

| Header | 24 bytes |

| Order Slot 0 | 29 bytes |

| Order Slot 1 | 29 bytes |

| Order Slot 2 | 29 bytes |

| ... | ... |

| Order Slot 99 | 29 bytes |



\## 4. Ring Buffer Header Layout



The header is defined using:



```python

HEADER = struct.Struct("<IIIIQ")

```



The format uses little-endian byte ordering.



The header occupies 24 bytes.



| Field | Data Type | Offset | Size |

|---|---|---:|---:|

| write\_index | uint32 | 0 | 4 bytes |

| item\_count | uint32 | 4 | 4 bytes |

| read\_index | uint32 | 8 | 4 bytes |

| unread\_count | uint32 | 12 | 4 bytes |

| sequence\_number | uint64 | 16 | 8 bytes |

| \*\*Total\*\* | | | \*\*24 bytes\*\* |



\### Header Field Description



\- \*\*write\_index:\*\* Indicates the next slot where the producer writes an order.

\- \*\*item\_count:\*\* Tracks the number of valid records currently retained in the ring buffer.

\- \*\*read\_index:\*\* Indicates the next unread slot for the consumer.

\- \*\*unread\_count:\*\* Tracks the number of orders waiting to be consumed.

\- \*\*sequence\_number:\*\* Tracks updates made by producer writes and consumer acknowledgements.



The header is accessed using `HEADER.pack\_into()` and `HEADER.unpack\_from()`.



\## 5. Binary Order Record Layout



The order schema is defined in `order\_schema.py`.



```python

ORDER\_STRUCT = struct.Struct("<QcdIQ")

```



Each order occupies exactly 29 bytes.



| Field | Data Type | Offset | Size |

|---|---|---:|---:|

| order\_id | uint64 | 0 | 8 bytes |

| side | char | 8 | 1 byte |

| price | double | 9 | 8 bytes |

| quantity | uint32 | 17 | 4 bytes |

| timestamp | uint64 | 21 | 8 bytes |

| \*\*Total\*\* | | | \*\*29 bytes\*\* |



\### Field Description



\- \*\*order\_id:\*\* Unique identifier of the order.

\- \*\*side:\*\* Represents the order direction: B for Buy and S for Sell.

\- \*\*price:\*\* Specifies the order price using a double-precision floating-point value.

\- \*\*quantity:\*\* Specifies the order quantity.

\- \*\*timestamp:\*\* Stores the order timestamp as a 64-bit unsigned integer.



The `<` prefix specifies little-endian byte ordering with standard field sizes and no automatic padding.



\### Packing and Unpacking



The `pack\_order()` function converts order fields into binary data.



```python

pack\_order(

&#x20;   order\_id,

&#x20;   side,

&#x20;   price,

&#x20;   quantity,

&#x20;   timestamp

)

```



The `unpack\_order()` function converts binary data back into a Python dictionary.



```python

unpack\_order(data)

```



This fixed-size format makes the record layout predictable for both Python and Cython consumers.



\## 6. Producer Operation



The producer uses the `push()` method of `MMapRingBuffer`.



The producer performs these operations:



1\. Converts the order into a 29-byte binary record.

2\. Acquires the shared lock.

3\. Reads the current header state.

4\. Calculates the target slot offset.

5\. Writes the record into the mapped memory.

6\. Advances the write index using circular indexing.

7\. Updates the item count and unread count.

8\. Increments the sequence number.

9\. Flushes the mapped file.

10\. Releases the lock.



The slot offset is calculated as:



```python

offset = header\_size + write\_index \* record\_size

```



Circular indexing is performed using:



```python

write\_index = (write\_index + 1) % capacity

```



When the buffer is full, the implementation can overwrite the oldest unread record when the read and write positions meet.



\## 7. Consumer Operation



The standard consumer uses `read\_next()`.



Its workflow is:



1\. Acquire the shared lock.

2\. Read the header.

3\. Check whether unread orders are available.

4\. Calculate the current record offset.

5\. Copy the record into Python bytes.

6\. Advance the read index.

7\. Decrease the unread count.

8\. Increment the sequence number.

9\. Flush the mapped file.

10\. Decode the record using `unpack\_order()`.



The consumer can also use `read\_all()` to retrieve retained records.



\### Cython Direct Memory Access



ChronosEngine also supports direct mmap consumption through the Cython matching engine's `consume\_mmap()` method.



The Cython consumer accesses the original mapped memory through the buffer protocol and reads individual binary fields using `memcpy()`.



It avoids creating a Python bytes object and dictionary for every consumed order before submitting the order to the matching engine.



The direct access uses these record offsets:



```text

Order ID   : offset 0

Side       : offset 8

Price      : offset 9

Quantity   : offset 17

Timestamp  : offset 21

```



The consumer processes an order before advancing the read cursor and acknowledging it.



This approach reduces Python-level serialization and object-creation overhead.



\## 8. Buffer Protocol



Python's buffer protocol allows objects to expose their underlying memory to other objects without requiring an intermediate Python bytes object.



The memory-mapped file supports this protocol.



A Cython typed memoryview can access the mapped memory:



```cython

cdef const unsigned char\[:] mapped = ring\_buffer.mm

```



The `mapped` memoryview provides access to the original mapped bytes.



The Cython consumer uses `memcpy()` to read individual fields into native C variables.



This avoids a full-record Python bytes copy during direct Cython consumption.



\### Important Distinction



Not every API in the current implementation is zero-copy.



\- `read\_next()` creates a Python bytes copy and then unpacks it.

\- `read\_all()` also copies individual records.

\- `read\_next\_view()` returns a memoryview of a newly packed copy, not the original mmap region.

\- `consume\_mmap()` reads fields directly from the original mapped memory but copies those field values into native variables.



Therefore, the Cython consumer provides direct mapped-memory access without per-record Python bytes and dictionary decoding. It should not be described as eliminating every memory copy.



\## 9. Synchronization and Concurrency



The ring buffer uses a separate lock file for process-shared synchronization on Windows.



The implementation uses:



```python

msvcrt.locking()

```



The `\_locked()` context manager acquires a one-byte lock before accessing shared memory and releases it afterward.



Both producer and consumer use this lock to prevent simultaneous conflicting updates.



The lock protects:



\- Header reads and writes.

\- Order record writes.

\- Order record reads.

\- Read and write cursor updates.

\- Unread count updates.



In the Cython consumer, the lock remains held while the order is processed and acknowledged. This prevents the producer from overwriting the slot while the consumer is using it.



This synchronization approach prioritizes data consistency but can block the producer while matching takes place.



\## 10. Performance Considerations



The memory-mapped ring buffer provides several performance benefits:



\- Fixed-size binary records reduce serialization overhead.

\- Shared file-backed memory supports communication between processes.

\- Circular indexing avoids continuously allocating new record slots.

\- Direct Cython access reduces Python-level object creation.

\- Native field decoding avoids full-record Python deserialization in the direct consumer path.



However, performance depends on:



\- Ring-buffer capacity.

\- Producer and consumer speeds.

\- Lock contention.

\- File flush frequency.

\- Python and Cython processing overhead.



The current locking strategy may become a bottleneck at high order rates. Further optimization could explore batch consumption and reservation/acknowledgement protocols.



\## 11. Limitations and Future Improvements



The current implementation has the following limitations:



1\. The synchronization mechanism uses Windows-specific `msvcrt` locking.

2\. The producer may overwrite the oldest unread record when the buffer is full.

3\. Holding the shared lock during matching can block the producer.

4\. A process crash between matching an order and acknowledging it can cause that order to be replayed after recovery.

5\. The implementation does not provide transactional exactly-once processing.

6\. The standard Python read methods still create copies of record data.



Possible future improvements include:



\- Cross-platform synchronization support.

\- Batch-based consumer processing.

\- Improved producer-consumer coordination.

\- Crash recovery and replay protection.

\- Performance benchmarking under concurrent workloads.



\## 12. Conclusion



ChronosEngine implements IPC using a memory-mapped circular ring buffer and a fixed-size binary order schema.



The 24-byte header manages buffer state, while each order occupies 29 bytes. A shared lock file coordinates producer and consumer access.



The Cython matching engine can read individual fields directly from the original mapped memory using the Python buffer protocol and native memory operations.



This design reduces Python-level serialization overhead and provides a foundation for efficient order communication between independent processes.

