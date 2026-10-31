
import struct

# Binary layout:
# Order ID | Side | Price | Quantity | Timestamp
ORDER_STRUCT = struct.Struct("<QcdIQ")


def pack_order(order_id, side, price, quantity, timestamp):
    if side not in ("B", "S"):
        raise ValueError("Side must be B or S")

    return ORDER_STRUCT.pack(
        order_id,
        side.encode("ascii"),
        price,
        quantity,
        timestamp
    )


def unpack_order(data):
    order_id, side, price, quantity, timestamp = (
        ORDER_STRUCT.unpack(data)
    )

    return {
        "order_id": order_id,
        "side": side.decode("ascii"),
        "price": price,
        "quantity": quantity,
        "timestamp": timestamp
    }


if __name__ == "__main__":
    data = pack_order(
        1001, "B", 125.50, 10, 1720000000000
    )

    print("Packed bytes:", data)
    print("Order size:", ORDER_STRUCT.size, "bytes")
    print("Unpacked order:", unpack_order(data))
