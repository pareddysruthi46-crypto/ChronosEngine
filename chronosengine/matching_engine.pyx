
from libc.stdlib cimport malloc, free
from libc.string cimport memcpy
from libc.stdint cimport uint64_t, uint32_t
from .matching_engine cimport Order, OrderNode
from math import isfinite


cdef unsigned int _apply_fill(
    OrderNode* maker,
    unsigned int remaining,
) noexcept nogil:
    cdef unsigned int trade_quantity

    if remaining < maker.order.quantity:
        trade_quantity = remaining
    else:
        trade_quantity = maker.order.quantity

    maker.order.quantity -= trade_quantity
    return trade_quantity


cdef class OrderBookNode:
    cdef OrderNode* node

    def __cinit__(self):
        self.node = NULL

    def __dealloc__(self):
        if self.node != NULL:
            free(self.node)
            self.node = NULL

    def set_order(
        self,
        unsigned long long order_id,
        char side,
        double price,
        unsigned int quantity,
        unsigned long long timestamp,
    ):
        if self.node == NULL:
            self.node = <OrderNode*>malloc(sizeof(OrderNode))
            if self.node == NULL:
                raise MemoryError()

        self.node.order.order_id = order_id
        self.node.order.side = side
        self.node.order.price = price
        self.node.order.quantity = quantity
        self.node.order.timestamp = timestamp
        self.node.prev = NULL
        self.node.next = NULL

    def get_order(self):
        if self.node == NULL:
            raise ValueError("No order has been set")

        return {
            "order_id": self.node.order.order_id,
            "side": chr(self.node.order.side),
            "price": self.node.order.price,
            "quantity": self.node.order.quantity,
            "timestamp": self.node.order.timestamp,
        }


cdef class PriceLevelQueue:
    """Doubly-linked FIFO queue for orders at one price level."""

    cdef OrderNode* head
    cdef OrderNode* tail

    def __cinit__(self):
        self.head = NULL
        self.tail = NULL

    def __dealloc__(self):
        cdef OrderNode* current
        cdef OrderNode* following

        current = self.head

        while current != NULL:
            following = current.next
            free(current)
            current = following

        self.head = NULL
        self.tail = NULL

    cdef void add_order(self, Order order) except *:
        cdef OrderNode* node
        cdef OrderNode* current

        node = <OrderNode*>malloc(sizeof(OrderNode))
        if node == NULL:
            raise MemoryError()

        node.order = order
        node.prev = NULL
        node.next = NULL

        # Preserve timestamp priority; equal timestamps keep insertion order.
        current = self.tail

        while (
            current != NULL
            and current.order.timestamp > order.timestamp
        ):
            current = current.prev

        if current == NULL:
            node.next = self.head

            if self.head != NULL:
                self.head.prev = node
            else:
                self.tail = node

            self.head = node

        else:
            node.prev = current
            node.next = current.next

            if current.next != NULL:
                current.next.prev = node
            else:
                self.tail = node

            current.next = node

    cdef void pop_head(self):
        cdef OrderNode* old_head

        if self.head == NULL:
            return

        old_head = self.head
        self.head = old_head.next

        if self.head != NULL:
            self.head.prev = NULL
        else:
            self.tail = NULL

        free(old_head)

    cdef bint remove_order(self, unsigned long long order_id):
        """Remove a specific active order from this price level."""
        cdef OrderNode* current

        current = self.head

        while current != NULL:
            if current.order.order_id == order_id:
                if current.prev != NULL:
                    current.prev.next = current.next
                else:
                    self.head = current.next

                if current.next != NULL:
                    current.next.prev = current.prev
                else:
                    self.tail = current.prev

                free(current)
                return True

            current = current.next

        return False

    cdef bint is_empty(self):
        return self.head == NULL


cdef class MatchingEngine:
    """Limit-order matching engine using price-time priority."""

    cdef dict _buys
    cdef dict _sells
    cdef list _trades
    cdef set _seen_order_ids

    def __cinit__(self):
        self._buys = {}
        self._sells = {}
        self._trades = []
        self._seen_order_ids = set()

    def insert_order(
        self,
        unsigned long long order_id,
        side,
        double price,
        unsigned int quantity,
        unsigned long long timestamp,
    ):
        """Insert an order directly into the active book without matching."""
        cdef Order incoming
        cdef PriceLevelQueue queue

        if side not in ("B", "S"):
            raise ValueError("side must be 'B' (buy) or 'S' (sell)")

        if not isfinite(price) or price <= 0:
            raise ValueError("price must be a finite positive number")

        if quantity == 0:
            raise ValueError("quantity must be greater than zero")

        if order_id in self._seen_order_ids:
            raise ValueError("order_id has already been used")

        incoming.order_id = order_id
        incoming.side = 66 if side == "B" else 83
        incoming.price = price
        incoming.quantity = quantity
        incoming.timestamp = timestamp

        if side == "B":
            if price not in self._buys:
                self._buys[price] = PriceLevelQueue()

            queue = <PriceLevelQueue>self._buys[price]
        else:
            if price not in self._sells:
                self._sells[price] = PriceLevelQueue()

            queue = <PriceLevelQueue>self._sells[price]

        queue.add_order(incoming)
        self._seen_order_ids.add(order_id)

        return True

    def cancel_order(self, unsigned long long order_id):
        """Cancel an active order. Return True if cancelled, otherwise False."""
        cdef double price
        cdef PriceLevelQueue queue

        for price in list(self._buys.keys()):
            queue = <PriceLevelQueue>self._buys[price]

            if queue.remove_order(order_id):
                if queue.is_empty():
                    del self._buys[price]

                return True

        for price in list(self._sells.keys()):
            queue = <PriceLevelQueue>self._sells[price]

            if queue.remove_order(order_id):
                if queue.is_empty():
                    del self._sells[price]

                return True

        return False

    def submit_order(
        self,
        unsigned long long order_id,
        side,
        double price,
        unsigned int quantity,
        unsigned long long timestamp,
    ):
        """Submit an order and match it against the opposite side."""
        cdef char side_code
        cdef unsigned int original_quantity
        cdef unsigned int remaining
        cdef unsigned int filled
        cdef unsigned int trade_quantity
        cdef Order incoming
        cdef OrderNode* maker
        cdef PriceLevelQueue queue
        cdef double best_price

        if side not in ("B", "S"):
            raise ValueError("side must be 'B' (buy) or 'S' (sell)")

        if not isfinite(price) or price <= 0:
            raise ValueError("price must be a finite positive number")

        if quantity == 0:
            raise ValueError("quantity must be greater than zero")

        if order_id in self._seen_order_ids:
            raise ValueError("order_id has already been used")

        side_code = 66 if side == "B" else 83
        original_quantity = quantity
        remaining = quantity

        self._seen_order_ids.add(order_id)

        if side == "B":
            # Match the lowest-priced sell orders first.
            while remaining > 0 and self._sells:
                best_price = min(self._sells.keys())

                if price < best_price:
                    break

                queue = <PriceLevelQueue>self._sells[best_price]
                maker = queue.head

                if maker == NULL:
                    del self._sells[best_price]
                    continue

                trade_quantity = (
                    remaining
                    if remaining < maker.order.quantity
                    else maker.order.quantity
                )

                self._trades.append({
                    "buy_order_id": order_id,
                    "sell_order_id": maker.order.order_id,
                    "price": maker.order.price,
                    "quantity": trade_quantity,
                    "timestamp": timestamp,
                })

                with nogil:
                    trade_quantity = _apply_fill(maker, remaining)

                remaining -= trade_quantity

                if maker.order.quantity == 0:
                    queue.pop_head()

                if queue.is_empty():
                    del self._sells[best_price]

        else:
            # Match the highest-priced buy orders first.
            while remaining > 0 and self._buys:
                best_price = max(self._buys.keys())

                if price > best_price:
                    break

                queue = <PriceLevelQueue>self._buys[best_price]
                maker = queue.head

                if maker == NULL:
                    del self._buys[best_price]
                    continue

                trade_quantity = (
                    remaining
                    if remaining < maker.order.quantity
                    else maker.order.quantity
                )

                self._trades.append({
                    "buy_order_id": maker.order.order_id,
                    "sell_order_id": order_id,
                    "price": maker.order.price,
                    "quantity": trade_quantity,
                    "timestamp": timestamp,
                })

                with nogil:
                    trade_quantity = _apply_fill(maker, remaining)

                remaining -= trade_quantity

                if maker.order.quantity == 0:
                    queue.pop_head()

                if queue.is_empty():
                    del self._buys[best_price]

        if remaining > 0:
            incoming.order_id = order_id
            incoming.side = side_code
            incoming.price = price
            incoming.quantity = remaining
            incoming.timestamp = timestamp

            if side == "B":
                if price not in self._buys:
                    self._buys[price] = PriceLevelQueue()

                queue = <PriceLevelQueue>self._buys[price]
                queue.add_order(incoming)

            else:
                if price not in self._sells:
                    self._sells[price] = PriceLevelQueue()

                queue = <PriceLevelQueue>self._sells[price]
                queue.add_order(incoming)

        filled = original_quantity - remaining

        return {
            "order_id": order_id,
            "filled_quantity": filled,
            "remaining_quantity": remaining,
        }

    def consume_mmap(self, ring_buffer, unsigned int max_orders=0):
        """
        Read binary orders directly from the original mmap memory.

        max_orders=0 means consume all currently available orders.
        The ring-buffer lock is held until each order is processed
        and acknowledged.
        """
        cdef const unsigned char[:] mapped = ring_buffer.mm

        cdef uint64_t order_id
        cdef uint64_t timestamp
        cdef uint32_t quantity
        cdef char side_code
        cdef double price

        cdef unsigned int processed = 0
        cdef unsigned int write_index
        cdef unsigned int item_count
        cdef unsigned int read_index
        cdef unsigned int unread_count
        cdef unsigned int next_read_index
        cdef uint64_t sequence_number

        cdef Py_ssize_t offset
        cdef tuple state

        if ring_buffer.record_size != 29:
            raise ValueError("Unexpected mmap record size")

        if max_orders == 0:
            max_orders = 0xFFFFFFFF

        while processed < max_orders:

            with ring_buffer._locked():

                state = ring_buffer._get_state()

                (
                    write_index,
                    item_count,
                    read_index,
                    unread_count,
                    sequence_number,
                ) = state

                if unread_count == 0:
                    break

                offset = (
                    ring_buffer.header_size
                    + read_index * ring_buffer.record_size
                )

                # Decode directly from the original mmap bytes.
                memcpy(&order_id, &mapped[offset], 8)
                memcpy(&side_code, &mapped[offset + 8], 1)
                memcpy(&price, &mapped[offset + 9], 8)
                memcpy(&quantity, &mapped[offset + 17], 4)
                memcpy(&timestamp, &mapped[offset + 21], 8)

                if side_code != 66 and side_code != 83:
                    raise ValueError("Invalid side byte in mmap record")

                # Match the order before acknowledging it.
                self.submit_order(
                    order_id,
                    chr(side_code),
                    price,
                    quantity,
                    timestamp,
                )

                next_read_index = (
                    read_index + 1
                ) % ring_buffer.capacity

                ring_buffer.HEADER.pack_into(
                    ring_buffer.mm,
                    0,
                    write_index,
                    item_count,
                    next_read_index,
                    unread_count - 1,
                    sequence_number + 1,
                )

                ring_buffer.mm.flush()

                processed += 1

        return processed

    cdef list _get_side_orders(self, dict levels, bint descending):
        cdef list result = []
        cdef PriceLevelQueue queue
        cdef OrderNode* node
        cdef double level_price

        for level_price in sorted(levels.keys(), reverse=descending):
            queue = <PriceLevelQueue>levels[level_price]
            node = queue.head

            while node != NULL:
                result.append({
                    "order_id": node.order.order_id,
                    "side": chr(node.order.side),
                    "price": node.order.price,
                    "quantity": node.order.quantity,
                    "timestamp": node.order.timestamp,
                })
                node = node.next

        return result

    def get_order_book(self):
        return {
            "buys": self._get_side_orders(self._buys, True),
            "sells": self._get_side_orders(self._sells, False),
        }

    def get_trades(self):
        return list(self._trades)
