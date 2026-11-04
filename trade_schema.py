import struct

# Trade ID | Buy Order ID | Sell Order ID | Price | Quantity | Timestamp
TRADE_STRUCT = struct.Struct("<QQQdIQ")


def pack_trade(
    trade_id,
    buy_order_id,
    sell_order_id,
    price,
    quantity,
    timestamp
):
    if trade_id <= 0:
        raise ValueError("Trade ID must be positive")

    if buy_order_id <= 0 or sell_order_id <= 0:
        raise ValueError("Order IDs must be positive")

    if price <= 0:
        raise ValueError("Price must be positive")

    if quantity <= 0:
        raise ValueError("Quantity must be positive")

    if timestamp < 0:
        raise ValueError("Timestamp cannot be negative")

    return TRADE_STRUCT.pack(
        trade_id,
        buy_order_id,
        sell_order_id,
        price,
        quantity,
        timestamp
    )


def unpack_trade(data):
    (
        trade_id,
        buy_order_id,
        sell_order_id,
        price,
        quantity,
        timestamp
    ) = TRADE_STRUCT.unpack(data)

    return {
        "trade_id": trade_id,
        "buy_order_id": buy_order_id,
        "sell_order_id": sell_order_id,
        "price": price,
        "quantity": quantity,
        "timestamp": timestamp
    }


if __name__ == "__main__":
    data = pack_trade(1, 101, 202, 125.50, 5, 1720000000000)

    print("Packed bytes:", data)
    print("Trade record size:", TRADE_STRUCT.size, "bytes")
    print("Unpacked trade:", unpack_trade(data))