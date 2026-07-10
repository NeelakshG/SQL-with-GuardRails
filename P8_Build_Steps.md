# Project 8 — Text-to-SQL with Guardrails: Build Steps

Stack assumption: Python, SQLite (swap to Postgres later if wanted), FastAPI + Streamlit (matches P6), Claude API for the LLM calls. Adjust if you want something different.

## Layer 0 — Schema + Seed DB

1. Design a small realistic schema (aim for 4-6 tables so joins matter) — e.g. `customers`, `subscriptions`, `orders`, `products`, `payments`.
2. Write the DDL and load it into SQLite.
3. Write a seed script generating a few hundred rows with realistic distributions (dates spread across quarters, mixed customer tiers, some nulls) so answers aren't trivially guessable.
4. Write 15-20 natural-language test questions spanning:
   - simple lookups ("list customers in California")
   - aggregations ("how many enterprise customers signed up last quarter")
   - joins across 2-3 tables
   - ambiguous/trick questions (to stress-test Layer 4 later)
5. Hand-write the "correct" SQL + expected answer for each test question — this is your eval set for every later layer.

## Layer 1 — NL → SQL

6. Write a prompt template: system message with full schema (table/column names, types, foreign keys) + the user's question, asking for SQL only, structured output (e.g. JSON with a `sql` field).
7. Wire up the LLM call (Claude API).
8. Run all 15-20 test questions through it, log generated SQL next to expected SQL. Don't fix edge cases yet — just confirm the basic pipe works.

## Layer 2 — Guardrails

9. Pick a SQL parser (`sqlglot` is the standard choice — parses to AST, works across dialects).
10. Write a validator that rejects: anything not a single `SELECT` statement, multiple statements (`;`-separated), DDL/DML keywords (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`), and unknown tables/columns not in an explicit allow-list.
11. Write a battery of adversarial test cases: prompt-injected multi-statement attempts, `UPDATE` disguised in a subquery, comments trying to hide a second statement, unicode tricks. Unit-test the validator against all of them.
12. Confirm the validator runs on every Layer-1 output before execution ever happens.

## Layer 3 — Sandboxed Execution

13. Create a read-only DB connection/role (SQLite: open in read-only URI mode; Postgres: dedicated read-only role).
14. Enforce a row cap (wrap query or truncate result set) and a statement timeout.
15. Wrap execution in error handling that returns a clean failure mode (not a stack trace) on timeout, row-cap trip, or DB error.

## Layer 4 — Semantic Verification + Confidence

16. Step A — self-explanation: ask the model to explain in plain English what the generated SQL computes.
17. Step B — compare that explanation against the original question (LLM-judge call, or embedding similarity as a cheaper first pass).
18. Step C — shape check: classify the question type (count / list / aggregate / yes-no) and confirm the result shape matches (e.g. "how many" should return one row, one number).
19. Step D — optional second-model critic: a separate call reviewing the SQL + question + result and flagging suspicious logic (wrong join direction, wrong filter column).
20. Combine A-D into a single confidence score (simple weighted rule is fine to start — don't over-engineer the formula).
21. Set a "needs review" threshold below which the answer is flagged instead of returned as fact.
22. Run the full eval set through Layers 1-4 end to end and check: does confidence actually track correctness? Adjust weights/threshold using your hand-labeled expected answers from step 5.

## Layer 5 — Surface

23. FastAPI endpoint: takes a question, returns `{answer, sql, confidence, needs_review}`.
24. Streamlit front end: question box, and a results view showing the answer, the SQL (collapsible), the confidence score, and a visible flag when `needs_review` is true.
25. Log every query (question, generated SQL, confidence, flagged or not) for later analysis.

## Wrap-up

26. Re-run the full eval set one more time end-to-end; write down accuracy, false-positive rate (confident but wrong), and false-negative rate (flagged but actually correct).
27. Write the README section covering the interview pitch and the honest limits of Layer 4 (it's a mitigation, not a guarantee) — this is your best interview material, so don't polish over the rough edges.
