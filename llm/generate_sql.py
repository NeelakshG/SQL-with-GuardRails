import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "..", "db", "schema.sql")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5-coder:3b"

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


def generate_sql(question, model=MODEL):
    """Calls the local Ollama model and returns a dict with the parsed
    sql/reasoning plus the raw response (for debugging malformed output)."""
    payload = {
        "model": model,
        "prompt": question,
        "system": build_system_prompt(),
        "format": "json",
        "stream": False,
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read())

    raw_text = body.get("response", "")
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
