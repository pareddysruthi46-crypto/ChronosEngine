import sqlite3
from pathlib import Path


SCHEMA_VERSION = 1

CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    buy_order_id INTEGER NOT NULL CHECK (buy_order_id > 0),
    sell_order_id INTEGER NOT NULL CHECK (sell_order_id > 0),
    price REAL NOT NULL CHECK (price >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    timestamp INTEGER NOT NULL CHECK (timestamp >= 0)
);
"""

CREATE_TIMESTAMP_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trades_timestamp
ON trades(timestamp);
"""

CREATE_BUY_ORDER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trades_buy_order
ON trades(buy_order_id);
"""

CREATE_SELL_ORDER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trades_sell_order
ON trades(sell_order_id);
"""

TRADE_FIELDS = (
    "buy_order_id",
    "sell_order_id",
    "price",
    "quantity",
    "timestamp",
)


def initialize_database(database_path="trade_ledger.db"):
    database_path = Path(database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)

    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")

        with connection:
            connection.execute(CREATE_TRADES_TABLE)
            connection.execute(CREATE_TIMESTAMP_INDEX)
            connection.execute(CREATE_BUY_ORDER_INDEX)
            connection.execute(CREATE_SELL_ORDER_INDEX)
            connection.execute(
                f"PRAGMA user_version = {SCHEMA_VERSION}"
            )
    finally:
        connection.close()

    return str(database_path)


def insert_trades_batch(database_path, trades):
    """Atomically insert a batch of matched trades into SQLite."""
    batch = list(trades)

    if not batch:
        return 0

    rows = []

    for trade in batch:
        if not isinstance(trade, dict):
            raise TypeError("Trade must be a dictionary")

        missing = set(TRADE_FIELDS).difference(trade)
        if missing:
            raise ValueError(
                f"Trade is missing fields: {sorted(missing)}"
            )

        rows.append(tuple(trade[field] for field in TRADE_FIELDS))

    connection = sqlite3.connect(database_path)

    try:
        with connection:
            connection.executemany(
                """
                INSERT INTO trades (
                    buy_order_id,
                    sell_order_id,
                    price,
                    quantity,
                    timestamp
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
    finally:
        connection.close()

    return len(rows)


def get_trade_count(database_path):
    connection = sqlite3.connect(database_path)

    try:
        return connection.execute(
            "SELECT COUNT(*) FROM trades"
        ).fetchone()[0]
    finally:
        connection.close()


if __name__ == "__main__":
    path = initialize_database()
    print("Trade ledger database initialized.")
    print("Database:", path)
    print("Schema version:", SCHEMA_VERSION)
