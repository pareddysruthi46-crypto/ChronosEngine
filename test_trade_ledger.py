import os
import sqlite3
import tempfile
import unittest

from chronosengine.trade_ledger import initialize_database


class TestTradeLedgerSchema(unittest.TestCase):

    def test_database_and_trades_table_are_created(self):
        with tempfile.TemporaryDirectory() as folder:
            database = os.path.join(folder, "trades.db")

            result = initialize_database(database)

            self.assertTrue(os.path.exists(database))
            self.assertEqual(result, os.path.abspath(database))

            connection = sqlite3.connect(database)

            try:
                columns = connection.execute(
                    "PRAGMA table_info(trades)"
                ).fetchall()

                column_names = [
                    column[1] for column in columns
                ]

                self.assertEqual(
                    column_names,
                    [
                        "trade_id",
                        "buy_order_id",
                        "sell_order_id",
                        "price",
                        "quantity",
                        "timestamp",
                    ],
                )
            finally:
                connection.close()

    def test_required_indexes_are_created(self):
        with tempfile.TemporaryDirectory() as folder:
            database = os.path.join(folder, "trades.db")
            initialize_database(database)

            connection = sqlite3.connect(database)

            try:
                indexes = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA index_list(trades)"
                    ).fetchall()
                }

                self.assertIn(
                    "idx_trades_timestamp", indexes
                )
                self.assertIn(
                    "idx_trades_buy_order", indexes
                )
                self.assertIn(
                    "idx_trades_sell_order", indexes
                )
            finally:
                connection.close()

    def test_trade_can_be_inserted_and_read(self):
        with tempfile.TemporaryDirectory() as folder:
            database = os.path.join(folder, "trades.db")
            initialize_database(database)

            connection = sqlite3.connect(database)

            try:
                connection.execute(
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
                    (101, 202, 125.50, 10, 1720000000000),
                )
                connection.commit()

                trade = connection.execute(
                    """
                    SELECT buy_order_id, sell_order_id,
                           price, quantity, timestamp
                    FROM trades
                    """
                ).fetchone()

                self.assertEqual(
                    trade,
                    (101, 202, 125.50, 10, 1720000000000),
                )
            finally:
                connection.close()

    def test_invalid_quantity_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            database = os.path.join(folder, "trades.db")
            initialize_database(database)

            connection = sqlite3.connect(database)

            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
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
                        (101, 202, 125.50, 0, 1720000000000),
                    )
            finally:
                connection.close()

    def test_initialization_is_safe_to_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            database = os.path.join(folder, "trades.db")

            initialize_database(database)
            initialize_database(database)

            connection = sqlite3.connect(database)

            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM trades"
                ).fetchone()[0]

                self.assertEqual(count, 0)
            finally:
                connection.close()


    def test_initialization_is_safe_to_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            database = os.path.join(folder, "trades.db")

            initialize_database(database)
            initialize_database(database)

            connection = sqlite3.connect(database)

            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM trades"
                ).fetchone()[0]

                self.assertEqual(count, 0)
            finally:
                connection.close()

    def test_database_uses_wal_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            database = os.path.join(folder, "trades.db")

            initialize_database(database)

            connection = sqlite3.connect(database)

            try:
                journal_mode = connection.execute(
                    "PRAGMA journal_mode"
                ).fetchone()[0]

                self.assertEqual(journal_mode.lower(), "wal")
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)