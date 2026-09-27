import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "llm"))

from llm_client import MODEL, call_llm  # noqa: E402


EXPLAIN_SYSTEM_PROMPT = """You are given a single SQL query and nothing else -- you do not know what
question it was meant to answer. Explain in 1-3 plain-English sentences exactly what this
query computes: which tables it reads, what filters it applies, and what it aggregates or
returns. Describe the query's actual logic precisely. Do not guess what question prompted it.

Respond with ONLY a JSON object of this exact shape, nothing else:
{"explanation": "<your plain-English explanation>"}
"""


def self_explain(sql, model=None):
    result = {"explanation": None, "raw_response": None, "parse_error": None}
    if not sql:
        result["parse_error"] = "no SQL provided"
        return result

    raw = call_llm(EXPLAIN_SYSTEM_PROMPT, sql, model)
    result["raw_response"] = raw
    try:
        parsed = json.loads(raw)
        result["explanation"] = parsed.get("explanation")
    except json.JSONDecodeError as e:
        result["parse_error"] = str(e)
    return result


JUDGE_SYSTEM_PROMPT = """You are a judge. You will be given a user's question and a plain-English
explanation of what a SQL query computes. Decide whether the explanation actually answers the
question -- not whether the SQL is well-written, just whether the thing being explained is the
thing that was asked.

Score from 0.0 (the explanation does not answer this question at all) to 1.0 (the explanation
fully and precisely answers this question). Be skeptical of explanations that are topically
related but check the wrong condition or the wrong entity.

Respond with ONLY a JSON object of this exact shape, nothing else:
{"score": <float between 0.0 and 1.0>, "reasoning": "<one sentence why>"}
"""


def judge_explanation(question, explanation, model=None):
    result = {"score": None, "reasoning": None, "raw_response": None, "parse_error": None}
    if not explanation:
        result["parse_error"] = "no explanation to judge"
        return result

    user = f"Question: {question}\nExplanation: {explanation}"
    raw = call_llm(JUDGE_SYSTEM_PROMPT, user, model)
    result["raw_response"] = raw
    try:
        parsed = json.loads(raw)
        result["score"] = float(parsed.get("score"))
        result["reasoning"] = parsed.get("reasoning")
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        result["parse_error"] = str(e)
    return result


def shape_check(question_type, result):
    is_scalar = not isinstance(result, list)

    if question_type == "aggregate":
        ok = is_scalar
        reason = None if ok else "aggregate question expects a single scalar result"
    elif question_type == "list":
        ok = not is_scalar
        reason = None if ok else "list question expects multiple rows/columns, got a single scalar"
    elif question_type == "yes_no":
        ok = is_scalar or (isinstance(result, list) and len(result) <= 1)
        reason = None if ok else "yes/no question expects a small, directly answerable result"
    else:
        ok, reason = True, None

    return ok, reason


CRITIC_SYSTEM_PROMPT = """You are a skeptical SQL reviewer. Your job is to find mistakes, not to
approve queries. Given a question, the SQL written to answer it, and the result that SQL
produced, look specifically for:
- wrong join direction or wrong join key
- filtering on the wrong column or wrong table
- counting or summing the wrong entity
- missing DISTINCT causing duplicate-inflated counts
- wrong date range or off-by-one date boundary

If you find a real issue, report it. If the query genuinely looks correct, say so -- do not
invent a problem that isn't there.

Respond with ONLY a JSON object of this exact shape, nothing else:
{"has_issue": <true or false>, "issue": "<description, or null if none>", "confidence_correct": <float 0.0-1.0>}
"""


def critic(question, sql, result, model=None):
    out = {"has_issue": None, "issue": None, "confidence_correct": None,
           "raw_response": None, "parse_error": None}
    if not sql:
        out["parse_error"] = "no SQL to critique"
        return out

    user = f"Question: {question}\nSQL: {sql}\nResult: {result}"
    raw = call_llm(CRITIC_SYSTEM_PROMPT, user, model)
    out["raw_response"] = raw
    try:
        parsed = json.loads(raw)
        out["has_issue"] = parsed.get("has_issue")
        out["issue"] = parsed.get("issue")
        out["confidence_correct"] = float(parsed.get("confidence_correct"))
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        out["parse_error"] = str(e)
    return out
