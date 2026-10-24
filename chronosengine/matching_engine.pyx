from libc.stdlib cimport malloc, free
from .matching_engine cimport Order, OrderNode


cdef class OrderBookNode:
    cdef OrderNode* node

    def __cinit__(self):
        self.node = NULL

    def __dealloc__(self):
        if self.node != NULL:
            free(self.node)
            self.node = NULL

    def set_order(self, unsigned long long order_id,
                  char side, double price,
                  unsigned int quantity,
                  unsigned long long timestamp):
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