
import mmap
import os
import struct

from order_schema import ORDER_STRUCT, pack_order, unpack_order


class MMapRingBuffer:
    """Fixed-capacity circular buffer backed by a memory-mapped file."""

    HEADER = struct.Struct("<II")  # write_index, item_count

    def __init__(self, filename, capacity=100):
        if capacity <= 0:
            raise ValueError("Capacity must be greater than zero")

        self.filename = filename
        self.capacity = capacity
        self.record_size = ORDER_STRUCT.size
        self.header_size = self.HEADER.size
        self.file_size = self.header_size + (
            capacity * self.record_size
        )

        # Create/reset the backing file to the required fixed size.
        self.file = open(filename, "w+b")
        self.file.truncate(self.file_size)
        self.file.flush()

        self.mm = mmap.mmap(self.file.fileno(), self.file_size)

        # Initially, no records are stored.
        self.HEADER.pack_into(self.mm, 0, 0, 0)

    def push(self, order):
        """Add an order; overwrite the oldest order when full."""
        record = pack_order(
            order["order_id"],
            order["side"],
            order["price"],
            order["quantity"],
            order["timestamp"],
        )

        write_index, item_count = self.HEADER.unpack_from(self.mm, 0)

        offset = self.header_size + (
            write_index * self.record_size
        )
        self.mm[offset:offset + self.record_size] = record

        write_index = (write_index + 1) % self.capacity
        item_count = min(item_count + 1, self.capacity)

        self.HEADER.pack_into(
            self.mm, 0, write_index, item_count
        )
        self.mm.flush()

    def read_all(self):
        """Return stored orders from oldest to newest."""
        write_index, item_count = self.HEADER.unpack_from(self.mm, 0)

        start_index = (
            write_index - item_count
        ) % self.capacity

        orders = []

        for i in range(item_count):
            index = (start_index + i) % self.capacity
            offset = self.header_size + (
                index * self.record_size
            )

            record = self.mm[offset:offset + self.record_size]
            orders.append(unpack_order(record))

        return orders

    def close(self):
        self.mm.close()
        self.file.close()


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

        print("Buffer capacity:", buffer.capacity)
        print("Record size:", buffer.record_size, "bytes")
        print("Backing file size:", buffer.file_size, "bytes")
        print("Stored orders (oldest to newest):")

        for order in buffer.read_all():
            print(order)

    finally:
        buffer.close()
