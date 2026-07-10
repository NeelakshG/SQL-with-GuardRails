# Project 8 — Text-to-SQL with Guardrails: Build Guide

**Stack:** Python · SQLite (swap to Postgres later if wanted) · FastAPI + Streamlit (matches P6) · Claude API for LLM calls.

**How to read this guide:** each layer expands the original steps with the *decisions you'll actually have to make*, the *gotchas that will bite you*, and a *definition of done* so you know when to stop and move on. No code — that's yours to write. The one rule that governs the whole project: **the LLM is the untrusted component.** Every layer exists because you assume the model's output could be wrong or malicious, and you refuse to rely on it behaving.

---

## Layer 0 — Schema + Seed DB

**Goal:** a small, realistic database and a hand-labeled question set. This is the foundation of every later layer — your eval set lives here, so don't rush it.

**Decisions to make:**

- *Pick a domain you can reason about instantly.* A SaaS/subscriptions domain (`customers`, `subscriptions`, `orders`, `products`, `payments`) is ideal because the natural-language questions write themselves ("how many enterprise customers churned last quarter") and you can eyeball whether an answer is right. Avoid a domain where you'd have to think hard about what the correct answer even is.
- *4–6 tables, and make the joins mean something.* You want at least one many-to-one (customers → subscriptions) and one that requires a 2–3 table join to answer (customer tier → orders → order value). If every question can be answered from one table, Layer 4 has nothing interesting to catch.
- *Design for ambiguity on purpose.* Include columns that are easy to confuse: a `signup_date` AND a `subscription_start_date`; an `amount` on both `orders` and `payments`; a `status` field with several values. These are the traps that make "valid SQL, wrong answer" possible — which is the whole point of the project.

**Gotchas:**

- *Trivially guessable data is useless for evaluation.* If all customers are "enterprise" or all dates are in one month, a wrong query can still return a right-looking number. Spread dates across quarters, mix tiers with realistic proportions (most customers are the cheap tier), and sprinkle in NULLs (a customer who never paid, an order with no shipment). NULLs specifically expose whether the model handles `COUNT(*)` vs `COUNT(column)` correctly.
- *Your seed data must be deterministic.* Seed the random generator so the DB is identical every run. Otherwise your hand-labeled "expected answers" drift and your eval set rots.
- *Write the expected answers by querying the DB, not by hand-arithmetic.* Run your own correct SQL against the seeded DB and record what it returns. This is your ground truth for the rest of the project — if it's wrong, everything downstream is measuring against a lie.

**The question set (steps 4–5) is the real deliverable here.** Aim for 15–20 questions in four buckets:

- *Simple lookups* ("list customers in California") — should almost always pass every layer; these are your sanity floor.
- *Aggregations* ("how many enterprise customers signed up last quarter") — the bread-and-butter case, tests date filtering and grouping.
- *Multi-table joins* ("total revenue per product category") — where the model most often joins the wrong way or on the wrong key.
- *Ambiguous / trick questions* ("who are our best customers?", "revenue last month" with no year) — these have no single correct answer, and they exist to stress-test Layer 4. Note *why* each one is a trap.

For each question, record: the question, the canonical correct SQL, the expected result, the question *type* (count/list/aggregate/yes-no — you'll need this in Layer 4's shape check), and for trick questions a note on the ambiguity.

**Definition of done:** you can run a script that rebuilds the DB from scratch, and you have a table (a CSV or JSON) of 15–20 questions each paired with correct SQL and expected answer. You could hand this to someone else and they'd know exactly what "correct" means.

---

## Layer 1 — NL → SQL

**Goal:** the naive pipe works end to end. **Deliberately under-invest here.** This is one LLM call and it's the least interesting part; the temptation to keep tuning the prompt is a trap that eats time meant for Layer 4.

**Decisions to make:**

- *Put the whole schema in the system prompt.* Table names, column names, types, and foreign-key relationships. The model cannot infer that `subscriptions.customer_id` references `customers.id` — you have to tell it. Include a one-line description per table if names are ambiguous.
- *Force structured output.* Ask for JSON with a `sql` field (and optionally a `reasoning` field). Parsing SQL out of prose or markdown fences is fragile; a structured field you can reliably extract. Claude supports this well — specify the exact shape you want.
- *Ask for SQL only, no commentary in the SQL field.* You'll do the explanation step separately in Layer 4 — keep generation and verification as independent calls so a model that's wrong in generation isn't also grading itself.

**Gotchas:**

- *Don't fix edge cases yet.* Run all 15–20 questions, log generated SQL next to your expected SQL, and just *observe*. Some will be wrong — that's fine and actually useful, because those failures are exactly what Layers 2 and 4 need to catch. If you polish the prompt until generation is perfect, you've accidentally removed your own test cases.
- *Log the raw model output, not just the parsed SQL.* When something breaks later you'll want to see exactly what came back, including malformed JSON or refusals.

**Definition of done:** all questions run through the model, you have generated-vs-expected SQL side by side in a log, and you've *resisted* tuning. You know your rough baseline (e.g. "12 of 18 look right") but you haven't acted on it.

---

## Layer 2 — Guardrails

**Goal:** structurally guarantee that only a safe, single, read-only query can ever reach the database. This is a **parsing problem, not an AI problem** — the whole value is that it's deterministic. You are not *asking* the model to behave; you are *making it impossible* for bad SQL to execute.

**Decisions to make:**

- *Use `sqlglot`.* It parses SQL into an AST across dialects and is the standard choice. Parsing is the key move: you inspect the *structure* of the query, not the string. String matching (e.g. "reject anything containing DROP") is defeated trivially by comments, casing, and whitespace — a real parser is not.
- *Build the validator as an ordered set of checks, each of which can reject:*
  - Exactly one statement. Multiple statements separated by `;` → reject. (This kills the classic "innocent SELECT; DROP TABLE" injection.)
  - The single statement must be a `SELECT` (or a read-only CTE that resolves to a select). Anything else → reject.
  - No DDL/DML anywhere in the tree: `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`. Because you're walking the AST, a write hidden inside a subquery is still caught.
  - Every table and column referenced must be on an explicit allow-list derived from your real schema. This catches hallucinated tables *and* narrows the attack surface.
- *Decide what "reject" does.* It should return a clean, structured refusal ("query blocked: multiple statements not allowed") — never execute, never fall through. This refusal is a first-class result, not an exception to swallow.

**Gotchas — and these are the interview gold:**

- *Comments hiding a second statement* (`SELECT 1 -- \n; DROP...`). A parser handles this; a regex might not. Test it.
- *`UPDATE`/`DELETE` disguised inside a subquery or CTE.* Walk the entire tree, not just the top node.
- *Unicode and homoglyph tricks* in identifiers. Normalize before comparing against your allow-list.
- *Stacked queries via the driver.* Even if your parser is perfect, make sure your DB driver isn't configured to allow multiple statements in one call — belt and suspenders.

**Step 11 (the adversarial test battery) is the single most valuable artifact in this layer.** Write a dedicated set of malicious/edge inputs — prompt-injected multi-statement attempts, disguised writes, comment tricks, unicode, references to tables not in the schema — and unit-test the validator against every one. Being able to say "here's my adversarial test suite and here's each attack it blocks" is exactly the concrete, senior-coded evidence interviewers want.

**Definition of done:** the validator runs on *every* Layer-1 output before any execution can happen, your adversarial suite is green (every attack blocked), and every legitimate query from your eval set passes. You can point to the test file and walk through the attacks.

---

## Layer 3 — Sandboxed Execution

**Goal:** defense-in-depth. Assume a bad query *slips past Layer 2* — this layer makes sure it still can't do damage or hang the database. The mindset: never trust a single layer.

**Decisions to make:**

- *Read-only at the connection level, not the query level.* SQLite: open the DB with a read-only URI. Postgres (later): create a dedicated role with only `SELECT` grants and connect as that role. This is stronger than parsing because it's enforced by the database itself — even a write that somehow reached the DB would be rejected.
- *Row cap.* Add or enforce a `LIMIT`, or truncate the result set after fetching N rows. Protects against "list every transaction" returning millions of rows and blowing up memory or the UI.
- *Statement timeout.* SQLite: use a query interrupt/timeout mechanism. Postgres: `statement_timeout`. A pathological query (accidental cross join) must be killed, not left to hang.

**Gotchas:**

- *Fail clean, never leak internals.* On a timeout, row-cap trip, or DB error, return a structured, human-readable failure — never a raw stack trace. A stack trace in the UI is both a bad experience and a security smell (it leaks schema/internals).
- *The row cap can silently distort answers.* If "how many orders" gets truncated to 100 rows, an aggregate could look wrong. Apply the cap to *result rows returned to the UI*, and be careful that aggregations (which return few rows) aren't accidentally capped in a way that changes the number. Know the difference between "limit rows displayed" and "limit rows scanned."

**Definition of done:** the read-only connection *physically cannot* write (test it — try to run an `UPDATE` through it and confirm the DB rejects it, independent of Layer 2). Timeouts and row caps fire correctly and return clean errors. You have belt-and-suspenders: two independent reasons a destructive query can't run.

---

## Layer 4 — Semantic Verification + Confidence

**Goal:** catch the query that is *perfectly valid, runs flawlessly, and answers the wrong question.* This is the hard, high-value, genuinely-imperfect core of the project. **Budget the most time here.** No library solves this — you're combining several weak, noisy signals into one usable score, and being honest that it's a mitigation, not a guarantee.

The philosophy: a single check gives you false confidence. You want *multiple independent signals* that tend to agree when the query is right and disagree when it's wrong. Each is individually unreliable; together they're informative.

**The four signals (steps 16–19):**

- *A — Self-explanation.* Ask the model to describe, in plain English, what the generated SQL actually computes. Critically: give it the SQL *without* the original question, so it explains the query on its own terms. If the query filters on the wrong column, a faithful explanation will say so ("counts customers created after Jan 1" when the question asked about *paying* customers).
- *B — Explanation-vs-question comparison.* Compare that plain-English explanation back to the original question. Start with an LLM-judge call ("does this explanation answer this question? score 0–1 with reasoning"). Embedding similarity is a cheaper first pass but is weaker — it catches topic drift, not logic errors. The LLM judge is the stronger signal; use embeddings only if you want a fast pre-filter.
- *C — Shape check.* This is your cheapest and most reliable signal, and it's pure code, not an LLM call. Using the question *type* you labeled in Layer 0: a "how many" must return one row with one number; a "list" should return multiple rows; a yes/no should be answerable from the result. A count query that returns 400 rows is provably answering the wrong question. Deterministic checks like this are worth more than they look.
- *D — Second-model critic (optional but strong).* A separate call that sees the question + SQL + result and specifically hunts for logic errors: wrong join direction, filtering the wrong column, counting the wrong entity, missing a `DISTINCT`. Frame it adversarially — "find what's wrong with this query" — so it doesn't just rubber-stamp.

**Combining into a confidence score (steps 20–21):**

- *Keep the formula dumb to start.* A simple weighted sum of the four signals is fine. Do NOT build an elaborate calibration model — that's over-engineering and interviewers will see through it. Weight the shape check heavily (it's reliable and cheap); weight the LLM signals less (they're noisy).
- *The "needs review" threshold is a product decision, not a math one.* Below the threshold, you flag the answer instead of presenting it as fact. Where you set it is a *tradeoff you should be able to articulate*: lower threshold = fewer false alarms but more wrong answers slip through; higher threshold = safer but more correct answers get needlessly flagged. Naming that tradeoff out loud is senior-coded.

**Gotchas:**

- *Don't let the model grade its own homework in one call.* Generation, explanation, and critique should be separate calls. A model that made a mistake generating will often repeat it when explaining if you show it the question at the same time.
- *Verification can be confidently wrong too.* The judge can approve a bad query. That's fine and expected — your claim is never "this is correct," it's "these independent signals agree, so confidence is higher." Own that limit; don't oversell it.

**Step 22 is the payoff and you must do it:** run the full eval set end to end and check whether confidence *actually tracks correctness*. Plot or tabulate confidence against your Layer-0 ground truth. Do the queries you know are wrong get low confidence? Do the right ones score high? Tune weights and threshold against this. If confidence is uncorrelated with correctness, the score is theater — this step is how you prove it isn't.

**Definition of done:** every answer carries a confidence score and a needs-review flag, and you have evidence (against your hand-labeled set) that low confidence correlates with wrong answers. You can state your false-positive and false-negative rates and explain the threshold tradeoff.

---

## Layer 5 — Surface

**Goal:** expose the whole pipeline through an API and a simple UI, and log everything.

**Decisions to make:**

- *FastAPI endpoint* takes a question and returns `{answer, sql, confidence, needs_review}`. Keep the contract flat and explicit — the `needs_review` boolean is the single most important field, because it encodes the entire safety philosophy in one flag.
- *Streamlit front end:* a question box; a results view showing the answer, the generated SQL (collapsible — power users want to see it, casual users don't), the confidence score, and a *visible, unmissable* flag when `needs_review` is true. The flagged state should look different, not just carry a small label — the point is that a low-confidence answer never gets mistaken for a trusted one.
- *Log every query* (question, generated SQL, confidence, flagged or not, and whether execution succeeded). This log is both a debugging tool and, in the interview narrative, "how I'd monitor this in production."

**Gotchas:**

- *Show the blocked/failed states, not just the happy path.* When Layer 2 rejects a query or Layer 3 times out, the UI should say so clearly. Demoing the *refusal* is more impressive than demoing a successful query — it's the whole thesis of the project made visible.

**Definition of done:** you can type a question and see answer + SQL + confidence + flag; a malicious question visibly gets blocked; a low-confidence answer is visibly flagged; every interaction is logged.

---

## Wrap-up

**Step 26 — measure honestly.** Re-run the full eval set end to end and write down three numbers: overall accuracy, false-positive rate (confident but wrong — the dangerous ones), and false-negative rate (flagged but actually correct — the annoying ones). These numbers ARE your interview credibility. A candidate who says "my verification catches most logic errors but here's the 15% it misses" beats one who claims perfection every time.

**Step 27 — the README is your best interview asset.** Write the one-line pitch, then a section on the *honest limits of Layer 4* — that semantic verification is a mitigation, not a guarantee, and exactly where it fails. Do not polish over the rough edges. The rough edges, described precisely, are the strongest signal you have that you understand what it means to put an LLM near a real system.

---

## The through-line to keep repeating

The LLM is the untrusted component. Layer 2 makes destructive queries structurally impossible (deterministic, provable). Layer 3 backs that up at the database level (defense in depth). Layer 4 attacks the harder, unsolved problem of "valid but wrong," combines weak signals into a calibrated confidence, and is honest about its ceiling. If you can walk an interviewer through those two threat models — *destructive* and *confidently wrong* — and your layered defense against each, you've delivered the whole project.
