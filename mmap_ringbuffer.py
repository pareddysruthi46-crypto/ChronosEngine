
import mmap
import struct

from order_schema import ORDER_STRUCT, pack_order, unpack_order


class MMapRingBuffer:
    """Fixed-capacity mmap ring buffer with consumer cursor tracking."""

    # write_index, item_count, read_index, unread_count
    HEADER = struct.Struct("<IIII")

    def __init__(self, filename, capacity=100):
        if capacity <= 0:
            raise ValueError("Capacity must be greater than zero")

        self.filename = filename
        self.capacity = capacity
        self.record_size = ORDER_STRUCT.size
        self.header_size = self.HEADER.size
        self.file_size = (
            self.header_size + capacity * self.record_size
        )

        self.file = open(filename, "w+b")
        self.file.truncate(self.file_size)
        self.file.flush()

        self.mm = mmap.mmap(self.file.fileno(), self.file_size)
        self.HEADER.pack_into(self.mm, 0, 0, 0, 0, 0)

    def _get_state(self):
        return self.HEADER.unpack_from(self.mm, 0)

    @property
    def read_index(self):
        """Index of the next unread record."""
        return self._get_state()[2]

    @property
    def unread_count(self):
        """Number of records waiting for the consumer."""
        return self._get_state()[3]

    def _write_record(self, record):
        """Write one packed record and update ring-buffer metadata."""
        if len(record) != self.record_size:
            raise ValueError(
                f"Record must be {self.record_size} bytes"
            )

        write_index, item_count, read_index, unread_count = (
            self._get_state()
        )

        offset = self.header_size + write_index * self.record_size
        self.mm[offset:offset + self.record_size] = record

        if item_count == self.capacity:
            if unread_count > 0 and read_index == write_index:
                read_index = (read_index + 1) % self.capacity
                unread_count -= 1
        else:
            item_count += 1

        write_index = (write_index + 1) % self.capacity
        unread_count += 1

        self.HEADER.pack_into(
            self.mm,
            0,
            write_index,
            item_count,
            read_index,
            unread_count,
        )

    def push(self, order):
        """Write a dictionary order, including its order type."""
        record = pack_order(
            order["order_id"],
            order["side"],
            order["price"],
            order["quantity"],
            order["timestamp"],
            order.get("order_type", "LIMIT"),
        )
        self._write_record(record)
        self.mm.flush()

    def push_packed(self, record):
        """Write an already-packed record without repacking it."""
        self._write_record(record)
        self.mm.flush()

    def read_next_view(self):
        """
        Return a zero-copy memoryview of the next unread record.

        Returns None when no unread records remain.
        The caller must release the returned view after using it.
        """
        write_index, item_count, read_index, unread_count = (
            self._get_state()
        )

        if unread_count == 0:
            return None

        offset = self.header_size + read_index * self.record_size

        parent_view = memoryview(self.mm)
        record_view = parent_view[offset:offset + self.record_size]
        parent_view.release()

        read_index = (read_index + 1) % self.capacity
        unread_count -= 1

        self.HEADER.pack_into(
            self.mm,
            0,
            write_index,
            item_count,
            read_index,
            unread_count,
        )

        return record_view

    def read_next(self):
        """Consume and decode the next unread order."""
        record_view = self.read_next_view()

        if record_view is None:
            return None

        try:
            return unpack_order(record_view)
        finally:
            record_view.release()

    def read_all(self):
        """Return all currently stored orders, oldest to newest."""
        write_index, item_count, read_index, unread_count = (
            self._get_state()
        )

        start_index = (write_index - item_count) % self.capacity
        orders = []

        for i in range(item_count):
            index = (start_index + i) % self.capacity
            offset = self.header_size + index * self.record_size

            record = self.mm[offset:offset + self.record_size]
            orders.append(unpack_order(record))

        return orders

    def close(self):
        """Flush pending changes and close mmap and file."""
        if not self.mm.closed:
            self.mm.flush()
            self.mm.close()

        if not self.file.closed:
            self.file.close()


if __name__ == "__main__":
    buffer = MMapRingBuffer("orders_buffer_test.dat", capacity=3)

    try:
        test_orders = [
            {
                "order_id": 1001,
                "side": "B",
                "price": 125.50,
                "quantity": 10,
                "timestamp": 1720000000001,
                "order_type": "MARKET",
            },
            {
                "order_id": 1002,
                "side": "S",
                "price": 126.50,
                "quantity": 20,
                "timestamp": 1720000000002,
                "order_type": "LIMIT",
            },
            {
                "order_id": 1003,
                "side": "B",
                "price": 127.50,
                "quantity": 30,
                "timestamp": 1720000000003,
                "order_type": "IOC",
            },
        ]

        for order in test_orders:
            buffer.push(order)

        print("Stored orders:")
        for order in buffer.read_all():
            print(order)

        print("Unread count:", buffer.unread_count)
        print("Consume one order:", buffer.read_next())
        print("Read cursor:", buffer.read_index)
        print("Remaining unread:", buffer.unread_count)

    finally:
        buffer.close()
