import json
import os
import unittest

from validate_sql import load_allowed_schema, validate

HERE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_PATH = os.path.join(HERE, "..", "eval", "questions.json")

SCHEMA = load_allowed_schema()


class ValidQueriesPass(unittest.TestCase):
    """Every canonical_sql in the eval set must be accepted -- the
    guardrail should never block a legitimately correct query."""

    def test_all_canonical_sql_accepted(self):
        with open(QUESTIONS_PATH) as f:
            data = json.load(f)

        for q in data["questions"]:
            sql = q.get("canonical_sql")
            if sql is None:
                continue
            ok, reason = validate(sql, SCHEMA)
            self.assertTrue(ok, f"{q['id']} was rejected: {reason}\nSQL: {sql}")

    def test_cte_and_alias_backreference(self):
        ok, reason = validate(
            "WITH recent AS (SELECT customer_id FROM customers) "
            "SELECT COUNT(*) AS n FROM recent",
            SCHEMA,
        )
        self.assertTrue(ok, reason)

    def test_order_by_output_alias(self):
        ok, reason = validate(
            "SELECT category, SUM(price) AS total FROM products "
            "GROUP BY category ORDER BY total DESC",
            SCHEMA,
        )
        self.assertTrue(ok, reason)

    def test_table_qualified_star(self):
        ok, reason = validate("SELECT s.* FROM subscriptions s", SCHEMA)
        self.assertTrue(ok, reason)

    def test_union_is_read_only_and_allowed(self):
        ok, reason = validate(
            "SELECT customer_id FROM customers WHERE tier = 'basic' "
            "UNION SELECT customer_id FROM customers WHERE tier = 'pro'",
            SCHEMA,
        )
        self.assertTrue(ok, reason)


class AdversarialBattery(unittest.TestCase):
    """Each case here is an attack this validator must block."""

    def assertRejected(self, sql):
        ok, reason = validate(sql, SCHEMA)
        self.assertFalse(ok, f"should have been rejected but passed: {sql}")
        return reason

    def test_multi_statement_injection(self):
        self.assertRejected("SELECT * FROM customers; DROP TABLE customers;")

    def test_comment_hidden_second_statement(self):
        self.assertRejected("SELECT * FROM customers -- innocent\n; DROP TABLE customers")

    def test_bare_update(self):
        self.assertRejected("UPDATE customers SET tier = 'enterprise'")

    def test_bare_delete(self):
        self.assertRejected("DELETE FROM customers")

    def test_bare_drop(self):
        self.assertRejected("DROP TABLE customers")

    def test_bare_insert(self):
        self.assertRejected("INSERT INTO customers (customer_id) VALUES (999)")

    def test_update_disguised_in_cte(self):
        self.assertRejected(
            "WITH t AS (UPDATE customers SET tier = 'enterprise' "
            "WHERE customer_id = 1 RETURNING *) SELECT * FROM t"
        )

    def test_delete_disguised_in_cte(self):
        self.assertRejected(
            "WITH t AS (DELETE FROM customers RETURNING *) SELECT * FROM t"
        )

    def test_insert_disguised_in_cte(self):
        self.assertRejected(
            "WITH t AS (INSERT INTO customers (customer_id, name, email, state, tier, signup_date) "
            "VALUES (999, 'x', 'x@example.com', 'CA', 'basic', '2025-01-01') RETURNING *) "
            "SELECT * FROM t"
        )

    def test_pragma(self):
        self.assertRejected("PRAGMA table_info(customers)")

    def test_attach_database(self):
        self.assertRejected("ATTACH DATABASE 'evil.db' AS evil")

    def test_unicode_homoglyph_table_name(self):
        # Cyrillic 'а' (U+0430) standing in for Latin 'a' in "customers"
        sql = "SELECT * FROM custаomers"
        self.assertRejected(sql)

    def test_hallucinated_table(self):
        self.assertRejected("SELECT * FROM users")

    def test_hallucinated_column(self):
        self.assertRejected("SELECT ssn FROM customers")

    def test_empty_sql(self):
        self.assertRejected("")

    def test_none_sql(self):
        self.assertRejected(None)

    def test_multiple_select_statements(self):
        self.assertRejected("SELECT * FROM customers; SELECT * FROM orders;")


if __name__ == "__main__":
    unittest.main()
