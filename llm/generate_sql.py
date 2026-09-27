import json
import os

from llm_client import MODEL, call_llm

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "..", "db", "schema.sql")

SYSTEM_PROMPT_TEMPLATE = """You are a SQL generator for a SQLite database. Given a natural-language question, produce a single read-only SELECT query that answers it.

Database schema:
{schema}

Rules:
- Only ever generate a single SELECT statement (a CTE is fine if it resolves to a SELECT).
- Never generate INSERT, UPDATE, DELETE, DROP, ALTER, or any other write/DDL statement.
- Use only the tables and columns shown above -- do not invent columns.
- If the question is ambiguous, still produce your best single-query attempt rather than refusing.
- Classify the question's expected result shape as one of: "aggregate" (a single number, e.g. a count or sum), "list" (multiple rows and/or columns), or "yes_no" (a yes/no answer).
- Respond with ONLY a JSON object of this exact shape, nothing else:
  {{"sql": "<the SQL query as a single string>", "reasoning": "<one sentence on your approach>", "type": "<aggregate|list|yes_no>"}}
- No markdown code fences, no commentary outside the JSON object.
"""


def load_schema():
    with open(SCHEMA_PATH) as f:
        return f.read()


def build_system_prompt():
    return SYSTEM_PROMPT_TEMPLATE.format(schema=load_schema())


def generate_sql(question, model=None):
    """Calls the LLM and returns a dict with the parsed sql/reasoning plus
    the raw response (for debugging malformed output)."""
    raw_text = call_llm(build_system_prompt(), question, model)
    result = {"sql": None, "reasoning": None, "type": None, "raw_response": raw_text, "parse_error": None}
    try:
        parsed = json.loads(raw_text)
        result["sql"] = parsed.get("sql")
        result["reasoning"] = parsed.get("reasoning")
        result["type"] = parsed.get("type")
    except json.JSONDecodeError as e:
        result["parse_error"] = str(e)
    return result


if __name__ == "__main__":
    import sys

    question = " ".join(sys.argv[1:]) or "How many customers are on the 'basic' tier?"
    print(json.dumps(generate_sql(question), indent=2))
