import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "guardrails"))
sys.path.insert(0, os.path.join(ROOT, "db"))
from generate_sql import generate_sql, MODEL  # noqa: E402
from validate_sql import load_allowed_schema, validate  # noqa: E402
from readonly import open_readonly_connection, execute_readonly  # noqa: E402

DB_PATH = os.path.join(ROOT, "db", "guardrails.db")
QUESTIONS_PATH = os.path.join(ROOT, "eval", "questions.json")
RESULTS_PATH = os.path.join(ROOT, "eval", "layer1_results.json")

ALLOWED_SCHEMA = load_allowed_schema()


def flatten(rows):
    """Mirrors eval/verify_questions.py: a single-cell result collapses
    to a bare scalar so it matches expected_result's recorded shape."""
    if len(rows) == 1 and len(rows[0]) == 1:
        return rows[0][0]
    return [list(r) for r in rows]


def try_execute(conn, sql):
    if not sql:
        return {"executed": False, "error": "no SQL generated", "result": None, "row_count": None}

    ok, reason = validate(sql, ALLOWED_SCHEMA)
    if not ok:
        return {"executed": False, "error": f"blocked by guardrail: {reason}", "result": None, "row_count": None}

    exec_result = execute_readonly(conn, sql)
    if not exec_result["ok"]:
        return {"executed": False, "error": exec_result["error"], "result": None, "row_count": None}

    return {
        "executed": True,
        "error": None,
        "result": flatten(exec_result["rows"]),
        "row_count": exec_result["row_count"],
        "truncated": exec_result["truncated"],
    }


def matches_expected(q, exec_result):
    """None = trick question, no ground truth to judge against.
    True/False = whether the generated SQL's result matches expected."""
    if q.get("canonical_sql") is None:
        return None
    if not exec_result["executed"]:
        return False
    if "expected_result" in q and q["expected_result"] is not None:
        return exec_result["result"] == q["expected_result"]
    if "expected_row_count" in q:
        return exec_result.get("row_count") == q["expected_row_count"]
    return False


def main():
    with open(QUESTIONS_PATH) as f:
        data = json.load(f)

    conn = open_readonly_connection(DB_PATH)
    results = []
    n_judged = 0
    n_correct = 0

    for q in data["questions"]:
        print(f"[{q['id']}] {q['question']}")
        gen = generate_sql(q["question"])
        exec_result = try_execute(conn, gen["sql"])
        correct = matches_expected(q, exec_result)

        if correct is not None:
            n_judged += 1
            if correct:
                n_correct += 1

        results.append({
            "id": q["id"],
            "bucket": q["bucket"],
            "question": q["question"],
            "canonical_sql": q.get("canonical_sql"),
            "generated_sql": gen["sql"],
            "generated_reasoning": gen["reasoning"],
            "raw_model_response": gen["raw_response"],
            "parse_error": gen["parse_error"],
            "execution": exec_result,
            "correct": correct,
        })

    conn.close()

    with open(RESULTS_PATH, "w") as f:
        json.dump({"model": MODEL, "results": results}, f, indent=2)

    n_trick = len(results) - n_judged
    print(f"\nModel: {MODEL}")
    print(f"Baseline: {n_correct}/{n_judged} correct (against questions with a canonical answer)")
    print(f"({n_trick} trick/ambiguous questions excluded from grading)")
    print(f"Full log written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
