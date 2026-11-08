import psutil


def summarize_trade_counters(trades):
    """Count executions and buy/sell order participation separately."""
    trades = trades or []

    return {
        "executions": len(trades),
        "buy_participations": sum(
            1 for trade in trades
            if trade.get("buy_order_id") is not None
        ),
        "sell_participations": sum(
            1 for trade in trades
            if trade.get("sell_order_id") is not None
        ),
    }


def get_buffer_telemetry(buffer):
    """Return real shared-memory buffer statistics, if connected."""
    if buffer is None:
        return None

    try:
        stats = buffer.get_stats()

        return {
            "capacity": stats.get("capacity"),
            "unread": stats.get("unread"),
            "available": stats.get("available"),
            "allocated_bytes": getattr(buffer, "file_size", None),
        }
    except (AttributeError, OSError, RuntimeError):
        return None


def collect_system_health(
    engine,
    trades,
    order_buffer=None,
    trade_buffer=None,
):
    """Collect CPU, engine memory, buffer and execution statistics."""
    try:
        cpu_percent = psutil.cpu_percent(interval=None)
    except (OSError, RuntimeError):
        cpu_percent = None

    try:
        memory_pool = engine.get_memory_pool_stats()
    except (AttributeError, OSError, RuntimeError):
        memory_pool = None

    return {
        "cpu_percent": cpu_percent,
        "memory_pool": memory_pool,
        "order_buffer": get_buffer_telemetry(order_buffer),
        "trade_buffer": get_buffer_telemetry(trade_buffer),
        "trade_counters": summarize_trade_counters(trades),
    }
