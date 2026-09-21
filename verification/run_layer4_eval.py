import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "llm"))
sys.path.insert(0, os.path.join(ROOT, "guardrails"))
sys.path.insert(0, os.path.join(ROOT, "db"))

from generate_sql import generate_sql, MODEL  # noqa: E402
from readonly import open_readonly_connection  # noqa: E402
from run_eval import try_execute, matches_expected  # noqa: E402
from signals import self_explain, judge_explanation, shape_check, critic  # noqa: E402
from confidence import combine  # noqa: E402

DB_PATH = os.path.join(ROOT, "db", "guardrails.db")
QUESTIONS_PATH = os.path.join(ROOT, "eval", "questions.json")
RESULTS_PATH = os.path.join(ROOT, "eval", "layer4_results.json")


def run_layer4(q, sql, exec_result):
    if not exec_result["executed"]:
        return {
            "confidence": 0.0,
            "needs_review": True,
            "breakdown": None,
            "signals": {
                "explanation": None,
                "judge": None,
                "shape": {"ok": False, "reason": exec_result["error"]},
                "critic": None,
            },
        }

    result = exec_result["result"]

    explain = self_explain(sql)
    judge = judge_explanation(q["question"], explain["explanation"])
    shape_ok, shape_reason = shape_check(q["type"], result)
    crit = critic(q["question"], sql, result)

    combined = combine(
        shape_ok=shape_ok,
        judge_score=judge["score"],
        critic_has_issue=crit["has_issue"],
        critic_confidence=crit["confidence_correct"],
    )
    combined["signals"] = {
        "explanation": explain,
        "judge": judge,
        "shape": {"ok": shape_ok, "reason": shape_reason},
        "critic": crit,
    }
    return combined


def report_calibration(results):
    judged = [r for r in results if r["correct"] is not None]
    correct = [r for r in judged if r["correct"]]
    wrong = [r for r in judged if not r["correct"]]

    def avg_conf(rows):
        return round(sum(r["confidence"] for r in rows) / len(rows), 3) if rows else None

    false_positives = [r for r in correct if r["needs_review"]]
    false_negatives = [r for r in wrong if not r["needs_review"]]

    print("\n=== Layer 4 calibration ===")
    print(f"Avg confidence on CORRECT answers: {avg_conf(correct)}  ({len(correct)} questions)")
    print(f"Avg confidence on WRONG answers:   {avg_conf(wrong)}  ({len(wrong)} questions)")
    print(f"False positives (correct but flagged needs_review): {len(false_positives)}/{len(correct)}")
    print(f"False negatives (WRONG but not flagged -- dangerous): {len(false_negatives)}/{len(wrong)}")


def main():
    with open(QUESTIONS_PATH) as f:
        data = json.load(f)

    conn = open_readonly_connection(DB_PATH)
    results = []

    for q in data["questions"]:
        print(f"[{q['id']}] {q['question']}")
        gen = generate_sql(q["question"])
        exec_result = try_execute(conn, gen["sql"])
        correct = matches_expected(q, exec_result)
        layer4 = run_layer4(q, gen["sql"], exec_result)

        results.append({
            "id": q["id"],
            "bucket": q["bucket"],
            "question": q["question"],
            "type": q["type"],
            "canonical_sql": q.get("canonical_sql"),
            "generated_sql": gen["sql"],
            "execution": exec_result,
            "correct": correct,
            "confidence": layer4["confidence"],
            "needs_review": layer4["needs_review"],
            "confidence_breakdown": layer4["breakdown"],
            "signals": layer4["signals"],
        })

    conn.close()

    with open(RESULTS_PATH, "w") as f:
        json.dump({"model": MODEL, "results": results}, f, indent=2)

    report_calibration(results)
    print(f"\nFull log written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
