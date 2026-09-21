import os
import re

import sqlglot
from sqlglot import exp

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "..", "db", "schema.sql")
DIALECT = "sqlite"

READ_ONLY_TOP_LEVEL = (exp.Select, exp.SetOperation)

FORBIDDEN_TYPES = (
    exp.Insert, exp.Update, exp.Delete,
    exp.Drop, exp.Create, exp.Alter, exp.TruncateTable,
    exp.Pragma, exp.Attach, exp.Grant, exp.Command,
)

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_allowed_schema(schema_path=SCHEMA_PATH):
    """table_name -> set(column_names), parsed straight from the real DDL."""
    with open(schema_path) as f:
        ddl = f.read()

    tables = {}
    for stmt in sqlglot.parse(ddl, read=DIALECT):
        if isinstance(stmt, exp.Create) and isinstance(stmt.this, exp.Schema):
            table_name = stmt.this.this.name.lower()
            columns = {
                col.this.name.lower()
                for col in stmt.this.expressions
                if isinstance(col, exp.ColumnDef)
            }
            tables[table_name] = columns
    return tables


def validate(sql, allowed_schema=None):
    """Returns (ok: bool, reason: str | None). Never executes the SQL."""
    if allowed_schema is None:
        allowed_schema = load_allowed_schema()

    if not sql or not sql.strip():
        return False, "no SQL provided"

    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except Exception as e:
        return False, f"failed to parse: {e}"

    if len(statements) != 1:
        return False, f"expected exactly one statement, found {len(statements)}"

    stmt = statements[0]

    if not isinstance(stmt, READ_ONLY_TOP_LEVEL):
        return False, f"only SELECT statements are allowed, got {type(stmt).__name__}"

    forbidden_hit = next(stmt.find_all(*FORBIDDEN_TYPES), None)
    if forbidden_hit is not None:
        return False, f"disallowed statement type found in query: {type(forbidden_hit).__name__}"

    allowed_tables = set(allowed_schema.keys())
    allowed_columns = set()
    for cols in allowed_schema.values():
        allowed_columns |= cols

    # CTE names and SELECT-list aliases are legitimate local references,
    # not real schema objects -- e.g. `... AS revenue ... ORDER BY revenue`.
    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    local_aliases = {a.alias.lower() for a in stmt.find_all(exp.Alias) if a.alias}

    for table in stmt.find_all(exp.Table):
        name = table.name
        if not IDENTIFIER_RE.match(name):
            return False, f"invalid table identifier: {name!r}"
        if name.lower() not in allowed_tables and name.lower() not in cte_names:
            return False, f"unknown table: {name!r}"

    for col in stmt.find_all(exp.Column):
        name = col.name
        if name == "*":  # table-qualified star, e.g. `s.*`
            continue
        if not IDENTIFIER_RE.match(name):
            return False, f"invalid column identifier: {name!r}"
        if name.lower() not in allowed_columns and name.lower() not in local_aliases:
            return False, f"unknown column: {name!r}"

    return True, None


if __name__ == "__main__":
    import sys

    sql = " ".join(sys.argv[1:]) or "SELECT * FROM customers"
    ok, reason = validate(sql)
    print("OK" if ok else f"REJECTED: {reason}")
