
from libc.stdlib cimport malloc, free
from .matching_engine cimport Order, OrderNode
from math import isfinite
from bisect import bisect_left


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

        # Preserve timestamp priority.
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
    """Limit-order matching engine with indexed price levels."""

    cdef list _buy_prices
    cdef list _buy_queues
    cdef list _sell_prices
    cdef list _sell_queues
    cdef list _trades
    cdef set _seen_order_ids

    def __cinit__(self):
        self._buy_prices = []
        self._buy_queues = []
        self._sell_prices = []
        self._sell_queues = []
        self._trades = []
        self._seen_order_ids = set()

    cdef Py_ssize_t _find_price(self, list prices, double price):
        """Find a price index using binary search."""
        return bisect_left(prices, price)

    cdef void _add_price_level(
        self,
        list prices,
        list queues,
        double price,
        PriceLevelQueue queue,
    ):
        """Insert a price and its queue at the matching sorted index."""
        cdef Py_ssize_t index

        index = self._find_price(prices, price)

        if index < len(prices) and prices[index] == price:
            return

        prices.insert(index, price)
        queues.insert(index, queue)

    cdef void _remove_price_level(
        self,
        list prices,
        list queues,
        double price,
    ):
        """Remove an empty price level from the index."""
        cdef Py_ssize_t index

        index = self._find_price(prices, price)

        if index < len(prices) and prices[index] == price:
            prices.pop(index)
            queues.pop(index)

    def insert_order(
        self,
        unsigned long long order_id,
        side,
        double price,
        unsigned int quantity,
        unsigned long long timestamp,
    ):
        """Insert an order directly into the active book."""
        cdef Order incoming
        cdef PriceLevelQueue queue
        cdef Py_ssize_t index

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
            index = self._find_price(self._buy_prices, price)

            if (
                index < len(self._buy_prices)
                and self._buy_prices[index] == price
            ):
                queue = <PriceLevelQueue>self._buy_queues[index]
            else:
                queue = PriceLevelQueue()
                self._add_price_level(
                    self._buy_prices,
                    self._buy_queues,
                    price,
                    queue,
                )
        else:
            index = self._find_price(self._sell_prices, price)

            if (
                index < len(self._sell_prices)
                and self._sell_prices[index] == price
            ):
                queue = <PriceLevelQueue>self._sell_queues[index]
            else:
                queue = PriceLevelQueue()
                self._add_price_level(
                    self._sell_prices,
                    self._sell_queues,
                    price,
                    queue,
                )

        queue.add_order(incoming)
        self._seen_order_ids.add(order_id)

        return True

    def cancel_order(self, unsigned long long order_id):
        """Cancel an active order."""
        cdef Py_ssize_t i
        cdef double price
        cdef PriceLevelQueue queue

        for i in range(len(self._buy_prices)):
            price = self._buy_prices[i]
            queue = <PriceLevelQueue>self._buy_queues[i]

            if queue.remove_order(order_id):
                if queue.is_empty():
                    self._remove_price_level(
                        self._buy_prices,
                        self._buy_queues,
                        price,
                    )
                return True

        for i in range(len(self._sell_prices)):
            price = self._sell_prices[i]
            queue = <PriceLevelQueue>self._sell_queues[i]

            if queue.remove_order(order_id):
                if queue.is_empty():
                    self._remove_price_level(
                        self._sell_prices,
                        self._sell_queues,
                        price,
                    )
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
            # Lowest sell price is at index zero.
            while remaining > 0 and self._sell_prices:
                best_price = self._sell_prices[0]

                if price < best_price:
                    break

                queue = <PriceLevelQueue>self._sell_queues[0]
                maker = queue.head

                if maker == NULL:
                    self._remove_price_level(
                        self._sell_prices,
                        self._sell_queues,
                        best_price,
                    )
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
                    self._remove_price_level(
                        self._sell_prices,
                        self._sell_queues,
                        best_price,
                    )

        else:
            # Highest buy price is at the last index.
            while remaining > 0 and self._buy_prices:
                best_price = self._buy_prices[-1]

                if price > best_price:
                    break

                queue = <PriceLevelQueue>self._buy_queues[-1]
                maker = queue.head

                if maker == NULL:
                    self._remove_price_level(
                        self._buy_prices,
                        self._buy_queues,
                        best_price,
                    )
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
                    self._remove_price_level(
                        self._buy_prices,
                        self._buy_queues,
                        best_price,
                    )

        if remaining > 0:
            incoming.order_id = order_id
            incoming.side = side_code
            incoming.price = price
            incoming.quantity = remaining
            incoming.timestamp = timestamp

            if side == "B":
                index = self._find_price(self._buy_prices, price)

                if (
                    index < len(self._buy_prices)
                    and self._buy_prices[index] == price
                ):
                    queue = <PriceLevelQueue>self._buy_queues[index]
                else:
                    queue = PriceLevelQueue()
                    self._add_price_level(
                        self._buy_prices,
                        self._buy_queues,
                        price,
                        queue,
                    )
            else:
                index = self._find_price(self._sell_prices, price)

                if (
                    index < len(self._sell_prices)
                    and self._sell_prices[index] == price
                ):
                    queue = <PriceLevelQueue>self._sell_queues[index]
                else:
                    queue = PriceLevelQueue()
                    self._add_price_level(
                        self._sell_prices,
                        self._sell_queues,
                        price,
                        queue,
                    )

            queue.add_order(incoming)

        filled = original_quantity - remaining

        return {
            "order_id": order_id,
            "filled_quantity": filled,
            "remaining_quantity": remaining,
        }

    cdef list _get_side_orders(
        self,
        list prices,
        list queues,
        bint descending,
    ):
        cdef list result = []
        cdef PriceLevelQueue queue
        cdef OrderNode* node
        cdef double level_price
        cdef Py_ssize_t i

        if descending:
            indices = range(len(prices) - 1, -1, -1)
        else:
            indices = range(len(prices))

        for i in indices:
            level_price = prices[i]
            queue = <PriceLevelQueue>queues[i]
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
            "buys": self._get_side_orders(
                self._buy_prices,
                self._buy_queues,
                True,
            ),
            "sells": self._get_side_orders(
                self._sell_prices,
                self._sell_queues,
                False,
            ),
        }

    def get_trades(self):
        return list(self._trades)
