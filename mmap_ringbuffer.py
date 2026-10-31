
import mmap
import os
import struct
import msvcrt
from contextlib import contextmanager

from order_schema import ORDER_STRUCT, pack_order, unpack_order


class MMapRingBuffer:
    """Memory-mapped ring buffer with process-shared synchronization."""

    # write_index, item_count, read_index, unread_count, sequence_number
    # Sequence number uses 64 bits.
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

        # Ensure the parent directory exists.
        parent = os.path.dirname(os.path.abspath(filename))
        os.makedirs(parent, exist_ok=True)

        # Create/open the shared lock file.
        self.lock_file = open(self.lock_filename, "a+b")
        self.lock_file.seek(0, os.SEEK_END)

        if self.lock_file.tell() == 0:
            self.lock_file.write(b"\0")
            self.lock_file.flush()

        self.file = None
        self.mm = None

        try:
            # Lock before checking or initializing the shared data file.
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
            if self.file is not None:
                self.file.close()
            self.lock_file.close()
            raise

    @contextmanager
    def _locked(self):
        """Acquire a one-byte lock shared by processes on Windows."""
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
        if self.mm is not None:
            self.mm.close()
            self.mm = None

        if self.file is not None:
            self.file.close()
            self.file = None

        if self.lock_file is not None:
            self.lock_file.close()
            self.lock_file = None


if __name__ == "__main__":
    buffer = MMapRingBuffer("orders_buffer.dat", capacity=3)

    try:
        for order_id in range(1001, 1005):
            buffer.push({
                "order_id": order_id,
                "side": "B" if order_id % 2 else "S",
                "price": 125.50 + order_id - 1001,
                "quantity": 10,
                "timestamp": 1720000000000 + order_id,
            })

        print("Stored orders:", buffer.read_all())
        print("Sequence number:", buffer.sequence_number)
        print("Unread count:", buffer.unread_count)
        print("Consume one order:", buffer.read_next())
        print("Read cursor:", buffer.read_index)
        print("Remaining unread:", buffer.unread_count)

    finally:
        buffer.close()
