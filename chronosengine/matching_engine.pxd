from libc.stdint cimport uint64_t, uint32_t


cdef struct Order:
    uint64_t order_id
    char side
    double price
    uint32_t quantity
    uint64_t timestamp


cdef struct OrderNode:
    Order order
    OrderNode* prev
    OrderNode* next