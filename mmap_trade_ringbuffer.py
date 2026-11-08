
import mmap
import os
import struct
import time
from contextlib import contextmanager

from trade_schema import TRADE_STRUCT, pack_trade, unpack_trade
from shutdown_signal import POISON_PILL
from buffer_watermarks import BufferWatermarkMonitor


# Header fields:
# write_index, item_count, read_index, unread_count, sequence_number
HEADER = struct.Struct("<IIIIQ")

# A valid trade cannot contain all-zero fields because trade IDs,
# order IDs, and quantity must be positive.

POISON_PILL_RECORD = TRADE_STRUCT.pack(
    0, 0, 0, 0.0, 0, 0)


class MmapTradeRingBuffer:
    """
    Memory-mapped outbound ring buffer for matched trade executions.

    Full-buffer policy:
        Raise BufferError instead of overwriting unread trades.

    Zero-copy API:
        read_next_view() returns an mmap-backed memoryview.
        Release the view before calling consume().

    Graceful shutdown:
        shutdown() writes a reserved poison-pill record.
        The consumer receives POISON_PILL after all pending trades.
        The marker is not consumed, keeping the buffer permanently shut down.
    """

    def __init__(self, filename, capacity):
        if capacity <= 0:
            raise ValueError("Capacity must be positive")

        self.filename = filename
        self.capacity = capacity
        self.record_size = TRADE_STRUCT.size
        self.header_size = HEADER.size
        self.file_size = self.header_size + (
            self.capacity * self.record_size
        )

        self.lock_filename = filename + ".lock"
        self._closed = False
        self._watermark_monitor = BufferWatermarkMonitor('trade')

        if not os.path.exists(filename):
            with open(filename, "wb") as file:
                file.truncate(self.file_size)
        else:
            if os.path.getsize(filename) != self.file_size:
                raise ValueError(
                    "Existing file size does not match capacity "
                    "and trade record size"
                )

        self.file = open(filename, "r+b")
        self.lock_file = open(self.lock_filename, "a+b")

        self.lock_file.seek(0, os.SEEK_END)
        if self.lock_file.tell() == 0:
            self.lock_file.write(b"\0")
            self.lock_file.flush()

        self.mm = mmap.mmap(
            self.file.fileno(),
            self.file_size,
            access=mmap.ACCESS_WRITE
        )

        with self._lock():
            header = self._read_header()

            if header == (0, 0, 0, 0, 0):
                self._write_header(0, 0, 0, 0, 0)

            elif (
                header[0] >= capacity
                or header[2] >= capacity
                or header[1] > capacity
                or header[3] > capacity
            ):
                raise ValueError("Invalid ring buffer header")

    @contextmanager
    def _lock(self):
        self.lock_file.seek(0)

        if os.name == "nt":
            import msvcrt

            msvcrt.locking(
                self.lock_file.fileno(),
                msvcrt.LK_LOCK,
                1
            )

            try:
                yield
            finally:
                self.lock_file.seek(0)
                msvcrt.locking(
                    self.lock_file.fileno(),
                    msvcrt.LK_UNLCK,
                    1
                )
        else:
            import fcntl

            fcntl.flock(
                self.lock_file.fileno(),
                fcntl.LOCK_EX
            )

            try:
                yield
            finally:
                fcntl.flock(
                    self.lock_file.fileno(),
                    fcntl.LOCK_UN
                )

    def _read_header(self):
        return HEADER.unpack(self.mm[:self.header_size])

    def _write_header(
        self,
        write_index,
        item_count,
        read_index,
        unread_count,
        sequence_number
    ):
        self.mm[:self.header_size] = HEADER.pack(
            write_index,
            item_count,
            read_index,
            unread_count,
            sequence_number
        )

    def _record_offset(self, index):
        return self.header_size + (
            index * self.record_size
        )

    def _contains_poison_locked(self):
        """
        Check whether the shutdown marker exists among unread records.
        Caller must hold the shared lock.
        """
        (
            write_index,
            item_count,
            read_index,
            unread_count,
            sequence_number
        ) = self._read_header()

        index = read_index

        for _ in range(unread_count):
            offset = self._record_offset(index)

            record = self.mm[
                offset:offset + self.record_size
            ]

            if record == POISON_PILL_RECORD:
                return True

            index = (index + 1) % self.capacity

        return False

    @property
    def is_shutdown(self):
        """Return True once a shutdown marker has been published."""
        with self._lock():
            return self._contains_poison_locked()

    def push_trade(
        self,
        trade_id,
        buy_order_id,
        sell_order_id,
        price,
        quantity,
        timestamp
    ):
        record = pack_trade(
            trade_id,
            buy_order_id,
            sell_order_id,
            price,
            quantity,
            timestamp
        )

        with self._lock():
            (
                write_index,
                item_count,
                read_index,
                unread_count,
                sequence_number
            ) = self._read_header()

            if self._contains_poison_locked():
                raise RuntimeError(
                    "Cannot publish trades after shutdown"
                )

            if unread_count >= self.capacity:
                raise BufferError(
                    "Trade ring buffer is full; "
                    "unread trades cannot be overwritten"
                )

            offset = self._record_offset(write_index)

            self.mm[
                offset:offset + self.record_size
            ] = record

            write_index = (write_index + 1) % self.capacity
            item_count = min(item_count + 1, self.capacity)
            unread_count += 1
            sequence_number += 1

            self._write_header(
                write_index,
                item_count,
                read_index,
                unread_count,
                sequence_number
            )
            self._watermark_monitor.update(
                unread_count, self.capacity
            )

            return sequence_number

    def shutdown(self, timeout=5.0, poll_interval=0.01):
        """
        Publish a poison pill after all pending trades.

        If the buffer is full, wait for the consumer to free a slot.
        Return True if this call publishes the marker.
        Return False if shutdown was already published.
        Raise TimeoutError if no slot becomes available in time.
        """
        if timeout is not None and timeout < 0:
            raise ValueError("timeout cannot be negative")

        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")

        deadline = (
            None if timeout is None
            else time.monotonic() + timeout
        )

        while True:
            with self._lock():
                (
                    write_index,
                    item_count,
                    read_index,
                    unread_count,
                    sequence_number
                ) = self._read_header()

                if self._contains_poison_locked():
                    return False

                if unread_count < self.capacity:
                    offset = self._record_offset(write_index)

                    self.mm[
                        offset:offset + self.record_size
                    ] = POISON_PILL_RECORD

                    write_index = (
                        write_index + 1
                    ) % self.capacity

                    item_count = min(
                        item_count + 1,
                        self.capacity
                    )

                    unread_count += 1
                    sequence_number += 1

                    self._write_header(
                        write_index,
                        item_count,
                        read_index,
                        unread_count,
                        sequence_number
                    )
                    self._watermark_monitor.update(
                        unread_count, self.capacity
                    )

                    return True

            if deadline is not None:
                remaining = deadline - time.monotonic()

                if remaining <= 0:
                    raise TimeoutError(
                        "Timed out waiting for free space "
                        "to publish shutdown marker"
                    )

                time.sleep(min(poll_interval, remaining))
            else:
                time.sleep(poll_interval)

    def read_next_view(self):
        """
        Return a zero-copy memoryview of the next unread trade.

        Returns:
            None: buffer is empty.
            POISON_PILL: shutdown marker reached.
            memoryview: normal trade record.

        Release a normal memoryview before calling consume().
        """
        with self._lock():
            (
                write_index,
                item_count,
                read_index,
                unread_count,
                sequence_number
            ) = self._read_header()

            if unread_count == 0:
                return None

            offset = self._record_offset(read_index)

            record = self.mm[
                offset:offset + self.record_size
            ]

            if record == POISON_PILL_RECORD:
                return POISON_PILL

            return memoryview(self.mm)[
                offset:offset + self.record_size
            ]

    def consume(self):
        """Consume the next normal trade, never the shutdown marker."""
        with self._lock():
            (
                write_index,
                item_count,
                read_index,
                unread_count,
                sequence_number
            ) = self._read_header()

            if unread_count == 0:
                raise IndexError(
                    "No unread trades to consume"
                )

            offset = self._record_offset(read_index)

            record = self.mm[
                offset:offset + self.record_size
            ]

            if record == POISON_PILL_RECORD:
                raise RuntimeError(
                    "Cannot consume the shutdown marker"
                )

            read_index = (read_index + 1) % self.capacity
            unread_count -= 1

            self._write_header(
                write_index,
                item_count,
                read_index,
                unread_count,
                sequence_number
            )
            self._watermark_monitor.update(
                unread_count, self.capacity
            )

    def read_next(self):
        """Copy and return the next trade, then consume it."""
        view = self.read_next_view()

        if view is None:
            return None

        if view is POISON_PILL:
            return POISON_PILL

        try:
            record = bytes(view)
        finally:
            view.release()

        trade = unpack_trade(record)
        self.consume()

        return trade

    def get_stats(self):
        with self._lock():
            (
                write_index,
                item_count,
                read_index,
                unread_count,
                sequence_number
            ) = self._read_header()

            metrics = self._watermark_monitor.update(
                unread_count, self.capacity
            )

            return {
                "capacity": self.capacity,
                "available": self.capacity - unread_count,
                "unread": unread_count,
                "write_index": write_index,
                "read_index": read_index,
                "sequence_number": sequence_number,
                "is_shutdown": self._contains_poison_locked(),
                **metrics
            }

    def close(self):
        if self._closed:
            return

        self.mm.close()
        self.lock_file.close()
        self.file.close()
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
