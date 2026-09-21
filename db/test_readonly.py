import time
import unittest

from readonly import open_readonly_connection, execute_readonly

SLOW_COUNT_SQL = """
WITH RECURSIVE cnt(x) AS (
  SELECT 1
  UNION ALL
  SELECT x + 1 FROM cnt WHERE x < 50000000
)
SELECT COUNT(*) FROM cnt
"""


class ReadOnlyConnection(unittest.TestCase):
    def setUp(self):
        self.conn = open_readonly_connection()

    def test_write_is_rejected_at_the_connection_level(self):
        result = execute_readonly(self.conn, "UPDATE customers SET tier = 'enterprise' WHERE customer_id = 1")
        self.assertFalse(result["ok"])
        self.assertIn("readonly", result["error"].lower())

    def test_delete_is_rejected_at_the_connection_level(self):
        result = execute_readonly(self.conn, "DELETE FROM customers WHERE customer_id = 1")
        self.assertFalse(result["ok"])
        self.assertIn("readonly", result["error"].lower())

    def test_normal_select_still_works(self):
        result = execute_readonly(self.conn, "SELECT COUNT(*) FROM customers")
        self.assertTrue(result["ok"])
        self.assertEqual(result["rows"], [[300]])


class RowCap(unittest.TestCase):
    def setUp(self):
        self.conn = open_readonly_connection()

    def test_large_result_is_truncated_to_the_cap(self):
        result = execute_readonly(self.conn, "SELECT * FROM customers a, orders b", row_cap=500)
        self.assertTrue(result["ok"])
        self.assertEqual(result["row_count"], 500)
        self.assertTrue(result["truncated"])

    def test_aggregation_result_is_not_affected_by_the_cap(self):
        result = execute_readonly(self.conn, "SELECT COUNT(*) FROM customers", row_cap=500)
        self.assertTrue(result["ok"])
        self.assertFalse(result["truncated"])
        self.assertEqual(result["row_count"], 1)

    def test_small_result_is_not_marked_truncated(self):
        result = execute_readonly(self.conn, "SELECT * FROM products", row_cap=500)
        self.assertTrue(result["ok"])
        self.assertFalse(result["truncated"])


class Timeout(unittest.TestCase):
    def setUp(self):
        self.conn = open_readonly_connection()

    def test_pathological_query_is_interrupted(self):
        start = time.monotonic()
        result = execute_readonly(self.conn, SLOW_COUNT_SQL, timeout_seconds=0.1)
        elapsed = time.monotonic() - start

        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertLess(elapsed, 2, "timeout should fire well before the query would finish on its own")

    def test_fast_query_is_not_affected_by_a_short_timeout_budget(self):
        result = execute_readonly(self.conn, "SELECT COUNT(*) FROM customers", timeout_seconds=5)
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
