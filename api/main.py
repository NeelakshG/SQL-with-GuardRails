import datetime
import json
import os
import sys

from fastapi import FastAPI
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

from pipeline import answer_question  # noqa: E402

LOG_PATH = os.path.join(ROOT, "logs", "queries.jsonl")

app = FastAPI(title="SQL-with-GuardRails")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: object = None
    sql: str | None = None
    confidence: float
    needs_review: bool
    blocked: bool
    error: str | None = None


def log_query(question, result):
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "question": question,
        "sql": result.get("sql"),
        "confidence": result.get("confidence"),
        "needs_review": result.get("needs_review"),
        "blocked": result.get("blocked"),
        "error": result.get("error"),
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    result = answer_question(req.question)
    log_query(req.question, result)
    return result
