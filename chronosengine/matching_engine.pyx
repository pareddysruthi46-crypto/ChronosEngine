from libc.stdlib cimport malloc, free
from libc.stddef cimport size_t
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


cdef class OrderNodePool:
    """Fixed-capacity pool of reusable C order nodes."""

    cdef OrderNode* _nodes
    cdef OrderNode* _free_head
    cdef Py_ssize_t _capacity
    cdef Py_ssize_t _available

    def __cinit__(self, Py_ssize_t capacity=100000):
        cdef Py_ssize_t i
        cdef OrderNode* node

        self._nodes = NULL
        self._free_head = NULL
        self._capacity = 0
        self._available = 0

        if capacity <= 0:
            raise ValueError("Pool capacity must be positive")

        # Prevent the allocation-size calculation from overflowing size_t.
        if <size_t>capacity > (<size_t>-1) // sizeof(OrderNode):
            raise OverflowError("Order node pool capacity is too large")

        self._nodes = <OrderNode*>malloc(
            <size_t>capacity * sizeof(OrderNode)
        )
        if self._nodes == NULL:
            raise MemoryError("Unable to allocate order node pool")

        self._capacity = capacity
        self._available = capacity

        # Link all pre-allocated nodes into the free list.
        for i in range(capacity):
            node = &self._nodes[i]
            node.prev = NULL
            node.next = self._free_head
            self._free_head = node

    def __dealloc__(self):
        if self._nodes != NULL:
            free(self._nodes)
            self._nodes = NULL
            self._free_head = NULL

    cdef OrderNode* acquire(self) except NULL:
        cdef OrderNode* node

        if self._free_head == NULL:
            raise MemoryError("Order node pool exhausted")

        node = self._free_head
        self._free_head = node.next

        node.prev = NULL
        node.next = NULL
        self._available -= 1

        return node

    cdef void release(self, OrderNode* node) noexcept:
        if node == NULL:
            return

        # Return the node to the pool's free list.
        node.prev = NULL
        node.next = self._free_head
        self._free_head = node
        self._available += 1

    def get_stats(self):
        return {
            "capacity": self._capacity,
            "available": self._available,
            "in_use": self._capacity - self._available,
        }


cdef class OrderBookNode:
    """Standalone order node backed by a one-node memory pool."""

    cdef OrderNode* node
    cdef OrderNodePool _pool

    def __cinit__(self):
        self.node = NULL
        self._pool = OrderNodePool(1)

    def __dealloc__(self):
        if self.node != NULL:
            self._pool.release(self.node)
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
            self.node = self._pool.acquire()

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
    """Doubly-linked queue using nodes from a shared memory pool."""

    cdef OrderNode* head
    cdef OrderNode* tail
    cdef OrderNodePool _pool

    def __cinit__(self, OrderNodePool pool):
        self.head = NULL
        self.tail = NULL
        self._pool = pool

    def __dealloc__(self):
        cdef OrderNode* current
        cdef OrderNode* following

        current = self.head

        while current != NULL:
            following = current.next
            self._pool.release(current)
            current = following

        self.head = NULL
        self.tail = NULL

    cdef void add_order(self, Order order) except *:
        cdef OrderNode* node
        cdef OrderNode* current

        # Acquire before changing queue links. If the pool is exhausted,
        # the existing queue remains unchanged.
        node = self._pool.acquire()

        node.order = order
        node.prev = NULL
        node.next = NULL

        # Preserve timestamp priority. Equal timestamps retain insertion order.
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

        self._pool.release(old_head)

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

                self._pool.release(current)
                return True

            current = current.next

        return False

    cdef bint is_empty(self):
        return self.head == NULL


cdef class MatchingEngine:
    """Limit-order matching engine using price-time priority and a node pool."""

    cdef dict _buys
    cdef dict _sells
    cdef list _trades
    cdef set _seen_order_ids
    cdef dict _active_orders
    cdef OrderNodePool _node_pool
    cdef object _outbound_ring_buffer

    def __cinit__(self, Py_ssize_t node_pool_size=100000):
        self._buys = {}
        self._sells = {}
        self._trades = []
        self._seen_order_ids = set()
        # order_id -> (side, price); deliberately stores no raw C pointers.
        self._active_orders = {}
        self._node_pool = OrderNodePool(node_pool_size)
        self._outbound_ring_buffer = None

    def set_output_ring_buffer(self, ring_buffer):
        """Attach or detach the outbound matched-trade ring buffer."""
        if ring_buffer is not None:
            if getattr(ring_buffer, "record_size", None) != 44:
                raise ValueError("Unexpected outbound trade record size")

        self._outbound_ring_buffer = ring_buffer
        return True

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
        cdef dict levels

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

        levels = self._buys if side == "B" else self._sells

        if price in levels:
            queue = <PriceLevelQueue>levels[price]
            queue.add_order(incoming)
        else:
            # Add to the dictionary only after node acquisition succeeds.
            queue = PriceLevelQueue(self._node_pool)
            queue.add_order(incoming)
            levels[price] = queue

        self._active_orders[order_id] = (side, price)
        self._seen_order_ids.add(order_id)

        return True

    def cancel_order(self, unsigned long long order_id):
        """Cancel an active order using the order-ID-to-price index."""
        cdef object location
        cdef object side
        cdef double price
        cdef PriceLevelQueue queue

        location = self._active_orders.get(order_id)
        if location is None:
            return False

        side, price = location

        if side == "B":
            queue = <PriceLevelQueue>self._buys[price]
            if queue.remove_order(order_id):
                if queue.is_empty():
                    del self._buys[price]
                del self._active_orders[order_id]
                return True
        else:
            queue = <PriceLevelQueue>self._sells[price]
            if queue.remove_order(order_id):
                if queue.is_empty():
                    del self._sells[price]
                del self._active_orders[order_id]
                return True

        # An index/book mismatch indicates an internal consistency problem.
        raise RuntimeError("Active-order index is inconsistent with the order book")

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
        cdef unsigned long long maker_order_id
        cdef dict levels

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

                maker_order_id = maker.order.order_id
                trade_quantity = (
                    remaining
                    if remaining < maker.order.quantity
                    else maker.order.quantity
                )

                if self._outbound_ring_buffer is None:
                    self._trades.append({
                        "buy_order_id": order_id,
                        "sell_order_id": maker_order_id,
                        "price": maker.order.price,
                        "quantity": trade_quantity,
                        "timestamp": timestamp,
                    })
                else:
                    self._outbound_ring_buffer.push_trade_values(
                        order_id,
                        maker_order_id,
                        maker.order.price,
                        trade_quantity,
                        timestamp,
                    )

                with nogil:
                    trade_quantity = _apply_fill(maker, remaining)

                remaining -= trade_quantity

                if maker.order.quantity == 0:
                    self._active_orders.pop(maker_order_id, None)
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

                maker_order_id = maker.order.order_id
                trade_quantity = (
                    remaining
                    if remaining < maker.order.quantity
                    else maker.order.quantity
                )

                if self._outbound_ring_buffer is None:
                    self._trades.append({
                        "buy_order_id": maker_order_id,
                        "sell_order_id": order_id,
                        "price": maker.order.price,
                        "quantity": trade_quantity,
                        "timestamp": timestamp,
                    })
                else:
                    self._outbound_ring_buffer.push_trade_values(
                        maker_order_id,
                        order_id,
                        maker.order.price,
                        trade_quantity,
                        timestamp,
                    )

                with nogil:
                    trade_quantity = _apply_fill(maker, remaining)

                remaining -= trade_quantity

                if maker.order.quantity == 0:
                    self._active_orders.pop(maker_order_id, None)
                    queue.pop_head()

                if queue.is_empty():
                    del self._buys[best_price]

        if remaining > 0:
            incoming.order_id = order_id
            incoming.side = side_code
            incoming.price = price
            incoming.quantity = remaining
            incoming.timestamp = timestamp

            levels = self._buys if side == "B" else self._sells

            if price in levels:
                queue = <PriceLevelQueue>levels[price]
                queue.add_order(incoming)
            else:
                # Avoid leaving an empty price level if the pool is exhausted.
                queue = PriceLevelQueue(self._node_pool)
                queue.add_order(incoming)
                levels[price] = queue

            self._active_orders[order_id] = (side, price)

        self._seen_order_ids.add(order_id)

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

    def get_memory_pool_stats(self):
        """Return memory-pool capacity and current node usage."""
        return self._node_pool.get_stats()
