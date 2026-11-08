import os
import sqlite3
import tempfile
import unittest

from chronosengine.trade_ledger import initialize_database


class TestTradeLedgerIndexes(unittest.TestCase):

    def test_indexes_cover_order_ids_and_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            database = os.path.join(folder, "trades.db")
            initialize_database(database)

            connection = sqlite3.connect(database)

            try:
                expected = {
                    "idx_trades_buy_order": "buy_order_id",
                    "idx_trades_sell_order": "sell_order_id",
                    "idx_trades_timestamp": "timestamp",
                }

                for index_name, expected_column in expected.items():
                    columns = connection.execute(
                        f"PRAGMA index_info({index_name})"
                    ).fetchall()

                    indexed_columns = [row[2] for row in columns]

                    self.assertEqual(
                        indexed_columns,
                        [expected_column],
                        f"{index_name} must index {expected_column}",
                    )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
