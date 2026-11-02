
import atexit
import mmap
import os
import struct
import msvcrt
from contextlib import contextmanager

from order_schema import ORDER_STRUCT, pack_order, unpack_order


class MMapRingBuffer:
    """Memory-mapped ring buffer with process-shared synchronization."""

    # write_index, item_count, read_index, unread_count, sequence_number
    HEADER = struct.Struct("<IIIIQ")

    def __init__(self, filename, capacity=100):
        if capacity <= 0:
            raise ValueError("Capacity must be greater than zero")

        self.filename = filename
        self.lock_filename = filename + ".lock"
        self.capacity = capacity
        self.record_size = ORDER_STRUCT.size
        self.header_size = self.HEADER.size
        self.file_size = self.header_size + capacity * self.record_size

        self.file = None
        self.mm = None
        self.lock_file = None
        self._closed = False

        try:
            # Ensure parent directory exists.
            parent = os.path.dirname(os.path.abspath(filename))
            os.makedirs(parent, exist_ok=True)

            # Create/open shared lock file.
            self.lock_file = open(self.lock_filename, "a+b")
            self.lock_file.seek(0, os.SEEK_END)

            if self.lock_file.tell() == 0:
                self.lock_file.write(b"\0")
                self.lock_file.flush()

            # Initialize or open the shared data file.
            with self._locked():
                if (
                    not os.path.exists(self.filename)
                    or os.path.getsize(self.filename) == 0
                ):
                    with open(self.filename, "w+b") as data_file:
                        data_file.truncate(self.file_size)
                        data_file.flush()

                    self.file = open(self.filename, "r+b")
                    self.mm = mmap.mmap(
                        self.file.fileno(), self.file_size
                    )

                    self.HEADER.pack_into(
                        self.mm, 0, 0, 0, 0, 0, 0
                    )
                    self.mm.flush()

                else:
                    actual_size = os.path.getsize(self.filename)

                    if actual_size != self.file_size:
                        raise ValueError(
                            f"Existing buffer size is {actual_size}, "
                            f"expected {self.file_size}. "
                            "Reopen with the original capacity."
                        )

                    self.file = open(self.filename, "r+b")
                    self.mm = mmap.mmap(
                        self.file.fileno(), self.file_size
                    )

        except Exception:
            if self.mm is not None:
                self.mm.close()
                self.mm = None

            if self.file is not None:
                self.file.close()
                self.file = None

            if self.lock_file is not None:
                self.lock_file.close()
                self.lock_file = None

            raise

        # Register cleanup only after successful initialization.
        atexit.register(self.close)

    @contextmanager
    def _locked(self):
        """Acquire a one-byte lock shared by processes on Windows."""
        if self._closed or self.lock_file is None:
            raise RuntimeError("Ring buffer is closed")

        self.lock_file.seek(0)
        msvcrt.locking(
            self.lock_file.fileno(), msvcrt.LK_LOCK, 1
        )

        try:
            yield
        finally:
            self.lock_file.seek(0)
            msvcrt.locking(
                self.lock_file.fileno(), msvcrt.LK_UNLCK, 1
            )

    def _get_state(self):
        return self.HEADER.unpack_from(self.mm, 0)

    @property
    def sequence_number(self):
        with self._locked():
            return self._get_state()[4]

    @property
    def read_index(self):
        with self._locked():
            return self._get_state()[2]

    @property
    def unread_count(self):
        with self._locked():
            return self._get_state()[3]

    def push(self, order):
        record = pack_order(
            order["order_id"],
            order["side"],
            order["price"],
            order["quantity"],
            order["timestamp"],
        )

        with self._locked():
            (
                write_index,
                item_count,
                read_index,
                unread_count,
                seq,
            ) = self._get_state()

            offset = (
                self.header_size + write_index * self.record_size
            )
            self.mm[offset:offset + self.record_size] = record

            if item_count == self.capacity:
                if unread_count > 0 and read_index == write_index:
                    read_index = (read_index + 1) % self.capacity
                    unread_count -= 1
            else:
                item_count += 1

            write_index = (write_index + 1) % self.capacity
            unread_count = min(unread_count + 1, self.capacity)
            seq += 1

            self.HEADER.pack_into(
                self.mm,
                0,
                write_index,
                item_count,
                read_index,
                unread_count,
                seq,
            )
            self.mm.flush()

    def read_next(self):
        with self._locked():
            (
                write_index,
                item_count,
                read_index,
                unread_count,
                seq,
            ) = self._get_state()

            if unread_count == 0:
                return None

            offset = (
                self.header_size + read_index * self.record_size
            )
            record = bytes(
                self.mm[offset:offset + self.record_size]
            )

            read_index = (read_index + 1) % self.capacity
            unread_count -= 1
            seq += 1

            self.HEADER.pack_into(
                self.mm,
                0,
                write_index,
                item_count,
                read_index,
                unread_count,
                seq,
            )
            self.mm.flush()

            return unpack_order(record)

    def read_next_view(self):
        """Return a memoryview of a copied record."""
        order = self.read_next()

        if order is None:
            return None

        record = pack_order(
            order["order_id"],
            order["side"],
            order["price"],
            order["quantity"],
            order["timestamp"],
        )
        return memoryview(record)

    def read_all(self):
        with self._locked():
            (
                write_index,
                item_count,
                read_index,
                unread_count,
                seq,
            ) = self._get_state()

            start_index = (
                write_index - item_count
            ) % self.capacity

            orders = []

            for i in range(item_count):
                index = (start_index + i) % self.capacity
                offset = (
                    self.header_size + index * self.record_size
                )
                record = bytes(
                    self.mm[offset:offset + self.record_size]
                )
                orders.append(unpack_order(record))

            return orders

    def close(self):
        """Flush and release all ring-buffer resources safely."""

        if self._closed:
            return

        # Do not close resources while another thread holds the lock.
        # The OS releases the process-level file lock when the handle closes.
        error = None

        if self.mm is not None:
            try:
                self.mm.flush()
            except Exception as exc:
                error = exc

            try:
                self.mm.close()
                self.mm = None
            except Exception as exc:
                if error is None:
                    error = exc

                # Keep resources available for a later cleanup attempt.
                raise error

        if self.file is not None:
            try:
                self.file.close()
                self.file = None
            except Exception as exc:
                if error is None:
                    error = exc

        if self.lock_file is not None:
            try:
                self.lock_file.close()
                self.lock_file = None
            except Exception as exc:
                if error is None:
                    error = exc

        if (
            self.mm is None
            and self.file is None
            and self.lock_file is None
        ):
            self._closed = True
            atexit.unregister(self.close)

        if error is not None:
            raise error

    def __enter__(self):
        if self._closed:
            raise RuntimeError("Ring buffer is already closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False
