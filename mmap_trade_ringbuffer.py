import mmap
import os
import struct
from contextlib import contextmanager

from trade_schema import TRADE_STRUCT, pack_trade, unpack_trade


# Header fields:
# write_index, item_count, read_index, unread_count, sequence_number
HEADER = struct.Struct("<IIIIQ")


class MmapTradeRingBuffer:
    """
    Memory-mapped outbound ring buffer for matched trade executions.

    Full-buffer policy:
        Raise BufferError instead of overwriting unread trades.

    Zero-copy API:
        read_next_view() returns a memoryview backed directly by mmap.
        After processing the view:
            view.release()
            consume()
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

            # Initialize a new or zero-filled header.
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
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)

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

            if unread_count >= self.capacity:
                raise BufferError(
                    "Trade ring buffer is full; unread trades cannot be overwritten"
                )

            offset = self.header_size + (
                write_index * self.record_size
            )

            self.mm[offset:offset + self.record_size] = record

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

            return sequence_number

    def read_next_view(self):
        """
        Return a zero-copy memoryview of the next unread trade.

        Do not call consume() until processing is complete.
        Release the returned view before calling consume().
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

            offset = self.header_size + (
                read_index * self.record_size
            )

            return memoryview(self.mm)[
                offset:offset + self.record_size
            ]

    def consume(self):
        """Mark the next unread trade as consumed."""
        with self._lock():
            (
                write_index,
                item_count,
                read_index,
                unread_count,
                sequence_number
            ) = self._read_header()

            if unread_count == 0:
                raise IndexError("No unread trades to consume")

            read_index = (read_index + 1) % self.capacity
            unread_count -= 1

            self._write_header(
                write_index,
                item_count,
                read_index,
                unread_count,
                sequence_number
            )

    def read_next(self):
        """Copy and return the next trade, then consume it."""
        view = self.read_next_view()

        if view is None:
            return None

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

            return {
                "capacity": self.capacity,
                "available": self.capacity - unread_count,
                "unread": unread_count,
                "write_index": write_index,
                "read_index": read_index,
                "sequence_number": sequence_number
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