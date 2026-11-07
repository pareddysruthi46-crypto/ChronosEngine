import math


def inject_whale_order(engine, order_id, side, price, quantity, timestamp):
    """
    Inject a large synthetic order and report its executions
    across the matching engine's price levels.
    """
    if side not in ("B", "S"):
        raise ValueError("side must be 'B' or 'S'")

    if not math.isfinite(price) or price <= 0:
        raise ValueError("price must be finite and positive")

    if quantity <= 0:
        raise ValueError("quantity must be positive")

    if timestamp < 0:
        raise ValueError("timestamp must be non-negative")

    previous_trade_count = len(engine.get_trades())

    result = engine.submit_order(
        order_id,
        side,
        price,
        quantity,
        timestamp,
    )

    new_trades = engine.get_trades()[previous_trade_count:]

    if side == "B":
        whale_trades = [
            trade for trade in new_trades
            if trade["buy_order_id"] == order_id
        ]
    else:
        whale_trades = [
            trade for trade in new_trades
            if trade["sell_order_id"] == order_id
        ]

    matched_price_levels = sorted({
        trade["price"] for trade in whale_trades
    })

    executed_quantity = sum(
        trade["quantity"] for trade in whale_trades
    )

    return {
        "order_id": order_id,
        "side": side,
        "requested_quantity": quantity,
        "filled_quantity": result["filled_quantity"],
        "remaining_quantity": result["remaining_quantity"],
        "executed_quantity": executed_quantity,
        "levels_hit": len(matched_price_levels),
        "matched_price_levels": matched_price_levels,
        "trades": whale_trades,
    }
