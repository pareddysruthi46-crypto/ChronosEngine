from libc.stdlib cimport malloc, free
from libc.stddef cimport size_t
from .matching_engine cimport Order, OrderNode
from .latency_metrics import RollingLatencyPercentiles
from math import isfinite
from time import perf_counter_ns


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

        if <size_t>capacity > (<size_t>-1) // sizeof(OrderNode):
            raise OverflowError("Order node pool capacity is too large")

        self._nodes = <OrderNode*>malloc(
            capacity * sizeof(OrderNode)
        )

        if self._nodes == NULL:
            raise MemoryError("Unable to allocate order node pool")

        self._capacity = capacity
        self._available = capacity

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

        node.prev = NULL
        node.next = self._free_head
        self._free_head = node
        self._available += 1

    cdef bint has_available(self):
        return self._available > 0

    def get_stats(self):
        return {
            "capacity": self._capacity,
            "available": self._available,
            "in_use": self._capacity - self._available,
        }


cdef class OrderBookNode:
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
    """Doubly-linked FIFO queue using nodes from a shared pool."""

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

        node = self._pool.acquire()
        node.order = order
        node.prev = NULL
        node.next = NULL

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
    """Limit-order matching engine with rolling nanosecond latency metrics."""

    cdef dict _buys
    cdef dict _sells
    cdef list _trades
    cdef list _sweep_events
    cdef set _seen_order_ids
    cdef dict _active_orders
    cdef OrderNodePool _node_pool

    cdef unsigned long long _last_ingress_ns
    cdef unsigned long long _last_egress_ns
    cdef unsigned long long _last_latency_ns
    cdef unsigned long long _total_latency_ns
    cdef unsigned long long _min_latency_ns
    cdef unsigned long long _max_latency_ns
    cdef unsigned long long _measured_orders
    cdef unsigned long long _successful_orders
    cdef unsigned long long _failed_orders

    cdef object _rolling_latency

    def __cinit__(self, latency_window_size=10000, node_pool_size=100000):
        self._buys = {}
        self._sells = {}
        self._trades = []
        self._sweep_events = []
        self._seen_order_ids = set()
        self._active_orders = {}
        self._node_pool = OrderNodePool(node_pool_size)

        self._last_ingress_ns = 0
        self._last_egress_ns = 0
        self._last_latency_ns = 0
        self._total_latency_ns = 0
        self._min_latency_ns = 0
        self._max_latency_ns = 0
        self._measured_orders = 0
        self._successful_orders = 0
        self._failed_orders = 0

        self._rolling_latency = RollingLatencyPercentiles(
            latency_window_size
        )

    cdef void _start_timing(self):
        self._last_ingress_ns = perf_counter_ns()

    cdef void _finish_timing(self, bint successful):
        cdef unsigned long long latency

        self._last_egress_ns = perf_counter_ns()
        latency = self._last_egress_ns - self._last_ingress_ns

        self._last_latency_ns = latency
        self._total_latency_ns += latency
        self._measured_orders += 1

        # Record successful and failed operation latencies.
        self._rolling_latency.add_sample(int(latency))

        if successful:
            self._successful_orders += 1
        else:
            self._failed_orders += 1

        if (
            self._min_latency_ns == 0
            or latency < self._min_latency_ns
        ):
            self._min_latency_ns = latency

        if latency > self._max_latency_ns:
            self._max_latency_ns = latency

    def insert_order(
        self,
        unsigned long long order_id,
        side,
        double price,
        unsigned int quantity,
        unsigned long long timestamp,
    ):
        """Insert an order directly into the book and measure its latency."""

        cdef Order incoming
        cdef PriceLevelQueue queue
        cdef bint successful = False

        self._start_timing()

        try:
            if side not in ("B", "S"):
                raise ValueError("side must be 'B' (buy) or 'S' (sell)")

            if not isfinite(price) or price <= 0:
                raise ValueError("price must be a finite positive number")

            if quantity == 0:
                raise ValueError("quantity must be greater than zero")

            if order_id in self._seen_order_ids:
                raise ValueError("order_id has already been used")

            if not self._node_pool.has_available():
                raise MemoryError("Order node pool exhausted")

            incoming.order_id = order_id
            incoming.side = 66 if side == "B" else 83
            incoming.price = price
            incoming.quantity = quantity
            incoming.timestamp = timestamp

            if side == "B":
                if price not in self._buys:
                    self._buys[price] = PriceLevelQueue(self._node_pool)

                queue = <PriceLevelQueue>self._buys[price]
            else:
                if price not in self._sells:
                    self._sells[price] = PriceLevelQueue(self._node_pool)

                queue = <PriceLevelQueue>self._sells[price]

            queue.add_order(incoming)
            self._active_orders[order_id] = (side, price)
            self._seen_order_ids.add(order_id)

            successful = True
            return True

        finally:
            self._finish_timing(successful)

    def cancel_order(self, unsigned long long order_id):
        """Cancel an active order using the order-ID-to-price index."""

        cdef object location
        cdef object side
        cdef double price
        cdef PriceLevelQueue queue
        cdef dict levels

        location = self._active_orders.get(order_id)

        if location is None:
            return False

        side, price = location
        levels = self._buys if side == "B" else self._sells

        if price not in levels:
            raise RuntimeError("Active-order index is inconsistent with the order book")

        queue = <PriceLevelQueue>levels[price]

        if not queue.remove_order(order_id):
            raise RuntimeError("Active-order index is inconsistent with the order book")

        if queue.is_empty():
            del levels[price]

        del self._active_orders[order_id]
        return True

    def submit_order(
        self,
        unsigned long long order_id,
        side,
        double price,
        unsigned int quantity,
        unsigned long long timestamp,
    ):
        """Submit and match an order, recording ingress-to-egress latency."""

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
        cdef bint successful = False
        cdef dict opposing_levels
        cdef list opposing_prices
        cdef double scan_price
        cdef PriceLevelQueue scan_queue
        cdef OrderNode* scan_node
        cdef unsigned int preflight_remaining
        cdef unsigned int reusable_nodes
        cdef list matched_price_levels
        cdef double last_sweep_price
        cdef unsigned int executed_quantity
        cdef bint has_last_sweep_price

        self._start_timing()

        try:
            if side not in ("B", "S"):
                raise ValueError("side must be 'B' (buy) or 'S' (sell)")

            if not isfinite(price) or price <= 0:
                raise ValueError("price must be a finite positive number")

            if quantity == 0:
                raise ValueError("quantity must be greater than zero")

            if order_id in self._seen_order_ids:
                raise ValueError("order_id has already been used")

            # Preflight matching without modifying the order book.
            # Fully consumed maker orders release nodes that can be reused.
            if side == "B":
                opposing_levels = self._sells
                opposing_prices = sorted(opposing_levels.keys())
            else:
                opposing_levels = self._buys
                opposing_prices = sorted(
                    opposing_levels.keys(),
                    reverse=True,
                )

            preflight_remaining = quantity
            reusable_nodes = 0

            for scan_price in opposing_prices:
                if side == "B":
                    if price < scan_price:
                        break
                else:
                    if price > scan_price:
                        break

                scan_queue = <PriceLevelQueue>opposing_levels[scan_price]
                scan_node = scan_queue.head

                while scan_node != NULL and preflight_remaining > 0:
                    if scan_node.order.quantity <= preflight_remaining:
                        preflight_remaining -= scan_node.order.quantity
                        reusable_nodes += 1
                    else:
                        preflight_remaining = 0

                    scan_node = scan_node.next

                if preflight_remaining == 0:
                    break

            if (
                preflight_remaining > 0
                and not self._node_pool.has_available()
                and reusable_nodes == 0
            ):
                raise MemoryError("Order node pool exhausted")

            side_code = 66 if side == "B" else 83
            original_quantity = quantity
            remaining = quantity

            matched_price_levels = []
            last_sweep_price = 0.0
            executed_quantity = 0
            has_last_sweep_price = False

            self._seen_order_ids.add(order_id)

            if side == "B":
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

                    if (
                        not has_last_sweep_price
                        or best_price != last_sweep_price
                    ):
                        matched_price_levels.append(best_price)
                        last_sweep_price = best_price
                        has_last_sweep_price = True

                    executed_quantity += trade_quantity

                    self._trades.append({
                        "buy_order_id": order_id,
                        "sell_order_id": maker.order.order_id,
                        "price": maker.order.price,
                        "quantity": trade_quantity,
                        "timestamp": timestamp,
                    })

                    remaining -= trade_quantity
                    maker.order.quantity -= trade_quantity

                    if maker.order.quantity == 0:
                        self._active_orders.pop(maker_order_id, None)
                        queue.pop_head()

                    if queue.is_empty():
                        del self._sells[best_price]

            else:
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

                    if (
                        not has_last_sweep_price
                        or best_price != last_sweep_price
                    ):
                        matched_price_levels.append(best_price)
                        last_sweep_price = best_price
                        has_last_sweep_price = True

                    executed_quantity += trade_quantity

                    self._trades.append({
                        "buy_order_id": maker.order.order_id,
                        "sell_order_id": order_id,
                        "price": maker.order.price,
                        "quantity": trade_quantity,
                        "timestamp": timestamp,
                    })

                    remaining -= trade_quantity
                    maker.order.quantity -= trade_quantity

                    if maker.order.quantity == 0:
                        self._active_orders.pop(maker_order_id, None)
                        queue.pop_head()

                    if queue.is_empty():
                        del self._buys[best_price]

            if len(matched_price_levels) >= 2:
                self._sweep_events.append({
                    "order_id": order_id,
                    "side": "BUY" if side == "B" else "SELL",
                    "levels_swept": len(matched_price_levels),
                    "executed_quantity": executed_quantity,
                    "matched_price_levels": list(matched_price_levels),
                    "timestamp": timestamp,
                })

            if remaining > 0:
                incoming.order_id = order_id
                incoming.side = side_code
                incoming.price = price
                incoming.quantity = remaining
                incoming.timestamp = timestamp

                if side == "B":
                    if price not in self._buys:
                        self._buys[price] = PriceLevelQueue(self._node_pool)

                    queue = <PriceLevelQueue>self._buys[price]
                    queue.add_order(incoming)

                else:
                    if price not in self._sells:
                        self._sells[price] = PriceLevelQueue(self._node_pool)

                    queue = <PriceLevelQueue>self._sells[price]
                    queue.add_order(incoming)

                self._active_orders[order_id] = (side, price)

            filled = original_quantity - remaining

            successful = True

            return {
                "order_id": order_id,
                "filled_quantity": filled,
                "remaining_quantity": remaining,
            }

        finally:
            self._finish_timing(successful)

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
        cdef list buys = self._get_side_orders(self._buys, True)
        cdef list sells = self._get_side_orders(self._sells, False)
        cdef object best_bid = max(self._buys.keys()) if self._buys else None
        cdef object best_ask = min(self._sells.keys()) if self._sells else None
        cdef object spread = None
        cdef bint is_crossed = False

        if best_bid is not None and best_ask is not None:
            spread = best_ask - best_bid
            is_crossed = best_bid >= best_ask

        return {
            "buys": buys,
            "sells": sells,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "is_crossed": bool(is_crossed),
        }

    def get_trades(self):
        return list(self._trades)

    def get_sweep_events(self):
        return [
            {
                **event,
                "matched_price_levels": list(event["matched_price_levels"]),
            }
            for event in self._sweep_events
        ]

    def get_memory_pool_stats(self):
        return self._node_pool.get_stats()

    def get_latency_metrics(self):
        """Return engine processing latency and rolling percentiles."""

        cdef double average_latency
        cdef dict percentile_metrics

        if self._measured_orders:
            average_latency = (
                self._total_latency_ns / self._measured_orders
            )
        else:
            average_latency = 0.0

        percentile_metrics = self._rolling_latency.get_percentiles()

        return {
            "last_ingress_ns": self._last_ingress_ns,
            "last_egress_ns": self._last_egress_ns,
            "last_latency_ns": self._last_latency_ns,
            "average_latency_ns": average_latency,
            "min_latency_ns": self._min_latency_ns,
            "max_latency_ns": self._max_latency_ns,

            "p50_latency_ns": percentile_metrics["p50_latency_ns"],
            "p90_latency_ns": percentile_metrics["p90_latency_ns"],
            "p99_latency_ns": percentile_metrics["p99_latency_ns"],
            "p999_latency_ns": percentile_metrics["p999_latency_ns"],

            "latency_window_size": percentile_metrics["latency_window_size"],
            "latency_sample_count": percentile_metrics["latency_sample_count"],
            "latency_samples_ns": self._rolling_latency.get_samples(),

            "measured_orders": self._measured_orders,
            "successful_orders": self._successful_orders,
            "failed_orders": self._failed_orders,
        }
