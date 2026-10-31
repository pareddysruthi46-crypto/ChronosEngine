
import struct

# Order ID | Side | Price | Quantity | Timestamp | Order Type
ORDER_STRUCT = struct.Struct("<QcdIQc")

ORDER_TYPE_CODES = {
    "MARKET": b"M",
    "LIMIT": b"L",
    "IOC": b"I",
}

ORDER_TYPE_NAMES = {
    b"M": "MARKET",
    b"L": "LIMIT",
    b"I": "IOC",
}


def pack_order(
    order_id, side, price, quantity, timestamp, order_type="LIMIT"
):
    if side not in ("B", "S"):
        raise ValueError("Side must be B or S")

    order_type = order_type.upper()

    if order_type not in ORDER_TYPE_CODES:
        raise ValueError("Order type must be MARKET, LIMIT, or IOC")

    return ORDER_STRUCT.pack(
        order_id,
        side.encode("ascii"),
        price,
        quantity,
        timestamp,
        ORDER_TYPE_CODES[order_type],
    )


def unpack_order(data):
    order_id, side, price, quantity, timestamp, type_code = (
        ORDER_STRUCT.unpack(data)
    )

    return {
        "order_id": order_id,
        "side": side.decode("ascii"),
        "price": price,
        "quantity": quantity,
        "timestamp": timestamp,
        "order_type": ORDER_TYPE_NAMES[type_code],
    }


if __name__ == "__main__":
    data = pack_order(
        1001, "B", 125.50, 10, 1720000000000, "IOC"
    )

    print("Packed bytes:", data)
    print("Order size:", ORDER_STRUCT.size, "bytes")
    print("Unpacked order:", unpack_order(data))
