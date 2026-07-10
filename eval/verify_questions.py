"""
Sanity check for eval/questions.json: re-runs every canonical_sql against
db/guardrails.db and confirms it still matches the recorded expected result.
Run after any change to db/seed.py or eval/questions.json.
"""
import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "..", "db", "guardrails.db")
QUESTIONS_PATH = os.path.join(HERE, "questions.json")


def flatten(rows):
    """A single-cell result (e.g. COUNT(*)) collapses to a bare scalar."""
    if len(rows) == 1 and len(rows[0]) == 1:
        return rows[0][0]
    return [list(r) for r in rows]


def main():
    with open(QUESTIONS_PATH) as f:
        data = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    failures = []

    for q in data["questions"]:
        sql = q.get("canonical_sql")
        if sql is None:
            continue  # ambiguous/trick question with no single correct answer

        rows = conn.execute(sql).fetchall()
        actual = flatten(rows)

        if "expected_result" in q and q["expected_result"] is not None:
            expected = q["expected_result"]
            if actual != expected:
                failures.append((q["id"], "expected_result", expected, actual))
        elif "expected_row_count" in q:
            actual_count = len(rows)
            if actual_count != q["expected_row_count"]:
                failures.append((q["id"], "expected_row_count",
                                 q["expected_row_count"], actual_count))

    conn.close()

    total = sum(1 for q in data["questions"] if q.get("canonical_sql"))
    if failures:
        print(f"{len(failures)}/{total} checked questions FAILED:")
        for qid, field, expected, actual in failures:
            print(f"  {qid}: {field} mismatch\n    expected: {expected}\n    actual:   {actual}")
        raise SystemExit(1)

    print(f"All {total} questions with canonical_sql match their recorded expected result.")


if __name__ == "__main__":
    main()
