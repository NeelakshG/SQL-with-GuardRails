import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "llm"))
sys.path.insert(0, os.path.join(HERE, "guardrails"))
sys.path.insert(0, os.path.join(HERE, "db"))
sys.path.insert(0, os.path.join(HERE, "verification"))

from generate_sql import generate_sql  # noqa: E402
from validate_sql import load_allowed_schema, validate  # noqa: E402
from readonly import open_readonly_connection, execute_readonly  # noqa: E402
from signals import self_explain, judge_explanation, shape_check, critic  # noqa: E402
from confidence import combine  # noqa: E402

DB_PATH = os.path.join(HERE, "db", "guardrails.db")
ALLOWED_SCHEMA = load_allowed_schema()


def flatten(rows):
    if len(rows) == 1 and len(rows[0]) == 1:
        return rows[0][0]
    return [list(r) for r in rows]


def answer_question(question):
    gen = generate_sql(question)

    if not gen["sql"]:
        return {
            "answer": None, "sql": None, "confidence": 0.0, "needs_review": True,
            "blocked": True, "error": gen["parse_error"] or "model returned no SQL",
        }

    ok, reason = validate(gen["sql"], ALLOWED_SCHEMA)
    if not ok:
        return {
            "answer": None, "sql": gen["sql"], "confidence": 0.0, "needs_review": True,
            "blocked": True, "error": f"blocked by guardrail: {reason}",
        }

    conn = open_readonly_connection(DB_PATH)
    try:
        exec_result = execute_readonly(conn, gen["sql"])
    finally:
        conn.close()

    if not exec_result["ok"]:
        return {
            "answer": None, "sql": gen["sql"], "confidence": 0.0, "needs_review": True,
            "blocked": False, "error": exec_result["error"],
        }

    result = flatten(exec_result["rows"])
    question_type = gen.get("type") or "list"

    explain = self_explain(gen["sql"])
    judge = judge_explanation(question, explain["explanation"])
    shape_ok, shape_reason = shape_check(question_type, result)
    crit = critic(question, gen["sql"], result)

    combined = combine(
        shape_ok=shape_ok,
        judge_score=judge["score"],
        critic_has_issue=crit["has_issue"],
        critic_confidence=crit["confidence_correct"],
    )

    return {
        "answer": result,
        "sql": gen["sql"],
        "confidence": combined["confidence"],
        "needs_review": combined["needs_review"],
        "blocked": False,
        "error": None,
        "truncated": exec_result["truncated"],
        "row_count": exec_result["row_count"],
        "signals": {
            "explanation": explain["explanation"],
            "judge_score": judge["score"],
            "judge_reasoning": judge["reasoning"],
            "shape_ok": shape_ok,
            "shape_reason": shape_reason,
            "critic_has_issue": crit["has_issue"],
            "critic_issue": crit["issue"],
        },
    }


if __name__ == "__main__":
    import json

    question = " ".join(sys.argv[1:]) or "How many customers are on the 'basic' tier?"
    print(json.dumps(answer_question(question), indent=2))
