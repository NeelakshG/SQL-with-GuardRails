# SQL with Guardrails — Text-to-SQL, Layered Defense

**One-line pitch:** a text-to-SQL system built on the assumption that the LLM is the untrusted component — every generated query passes through a deterministic parser that makes destructive SQL structurally impossible, a sandboxed read-only connection that backs that up independently, and a confidence-scoring layer that tries (and, honestly, sometimes fails) to catch queries that are syntactically valid but answer the wrong question.

## Architecture

| Layer | What it does | Where |
|---|---|---|
| 0 | Schema + seeded SQLite DB + 18 hand-labeled eval questions | `db/`, `eval/` |
| 1 | NL → SQL via a local Ollama model (`qwen2.5-coder:3b`) | `llm/generate_sql.py` |
| 2 | Deterministic guardrail — parses SQL with `sqlglot`, rejects anything but a single read-only `SELECT` | `guardrails/validate_sql.py` |
| 3 | Sandboxed execution — read-only DB connection, 500-row cap, 5s timeout | `db/readonly.py` |
| 4 | Semantic verification — self-explanation, LLM judge, shape check, adversarial critic, combined into one confidence score | `verification/` |
| 5 | FastAPI (`/ask`) + Streamlit UI, every query logged | `api/`, `ui/` |

`pipeline.py` wires all five layers together into one `answer_question(question)` call, used by both the API and the eval scripts.

## Running it

```
python db/seed.py                        # build db/guardrails.db
ollama pull qwen2.5-coder:3b              # once
python -m uvicorn api.main:app --port 8000
python -m streamlit run ui/app.py
```

To use Groq's hosted API instead of local Ollama, set `GROQ_API_KEY` (optionally `LLM_MODEL`, default `llama-3.3-70b-versatile`). The deployed Streamlit app reads it from the app's secrets.

To re-run the full eval set end to end (Layers 1-4, with grading): `python verification/run_layer4_eval.py`

## Final measured results

Last full run against the 18-question eval set (16 have a graded ground truth; 2 are deliberately unanswerable trick questions):

- **Overall accuracy: 6/16 (37.5%)** of gradable questions answered correctly
- **False positives — confident but wrong, the dangerous ones: 8/10 wrong answers (80%)** were presented with high confidence and never flagged for review
- **False negatives — flagged but actually correct, the annoying ones: 0/6 correct answers (0%)** were ever wrongly flagged

These numbers move somewhat between runs — see "Honest limits" below for why — but the shape is consistent: confidence tracks correctness *directionally* (correct answers score meaningfully higher on average than wrong ones), while the false-positive rate is high enough that this system should never be trusted to self-certify its own answers unsupervised.

## Honest limits of Layer 4

This is a mitigation, not a guarantee, and here's the concrete evidence for exactly where it falls short — found by actually running the pipeline, not by inspection:

**The critic and judge signals are individually weak.** Across a full eval run, the LLM judge's average score on *correct* answers (0.614) was statistically indistinguishable from its average on *wrong* answers (0.619) — essentially zero discriminating power on its own. The critic did separate better on average (1.0 vs 0.714), but on individual cases it repeatedly rubber-stamped real bugs: it approved Q11's query — which joined through `payments.status` instead of `orders.status`, the wrong table entirely, and even produced a duplicate row from a missing `DISTINCT` — with `has_issue: false, confidence_correct: 1.0`.

**Ambiguity detection doesn't exist.** Asking "who are our best customers?" (a deliberately unanswerable question — "best" has no single definition) produced a confident SQL query, a real table of names, and a **96% confidence score with no review flag**, live, in the running system. Layer 4 has no mechanism for recognizing that a question itself is underspecified; it can only judge whether a *given* SQL query's logic is internally consistent with a chosen interpretation.

**Not every "wrong" grade is a real logic bug.** Some of the false negatives above are grading artifacts rather than actual reasoning failures: a query that computed the exact correct revenue figures but omitted `ORDER BY` (row order mismatch against the exact-match grader), and one that computed the exact correct average but skipped `ROUND()` (a float-precision mismatch, not a wrong answer). A stricter eval harness would treat these as "correct, different formatting" rather than "wrong" — worth knowing, since it means the true logic-error rate is lower than the raw accuracy number implies, but it cuts the other way too: it means some of the *reported* false positives above aren't dangerous logic bugs at all.

**The eval baseline itself isn't perfectly reproducible.** Because generation runs against a non-deterministic local model (no fixed seed/temperature-0 constraint), re-running the identical eval set produces different generated SQL — and therefore a different accuracy number — from run to run (accuracy has ranged from roughly 35% to 56% across runs during development). Any single run's headline number should be read as one sample from a noisy process, not a fixed property of the system.

## The through-line

The LLM is the untrusted component throughout. Layer 2 makes destructive queries structurally impossible — deterministic, provable, verified with a 22-case adversarial test suite and confirmed live against a model that, when asked in plain English to delete customer records, actually tried. Layer 3 backs that up independently at the database level, so a bug in Layer 2 wouldn't be a single point of failure. Layer 4 attacks the much harder, genuinely unsolved problem of "valid SQL, wrong answer" — and the evidence above is presented honestly rather than polished over, because being able to say "here's exactly what my verification catches, and here's exactly what it misses and why" is stronger interview material than a claim of perfect accuracy.
