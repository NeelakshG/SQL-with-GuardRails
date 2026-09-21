import os
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(HERE, "guardrails.db")

ROW_CAP = 500
TIMEOUT_SECONDS = 5


def open_readonly_connection(db_path=DEFAULT_DB_PATH):
    """A write attempted on this connection is rejected by SQLite itself,
    independent of whatever guardrails/validate_sql.py already caught."""
    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def execute_readonly(conn, sql, row_cap=ROW_CAP, timeout_seconds=TIMEOUT_SECONDS):
    """Runs sql with a row cap and a wall-clock timeout. Never raises --
    callers always get a structured result, never a raw stack trace."""
    start = time.monotonic()

    def progress_handler():
        return 1 if (time.monotonic() - start) > timeout_seconds else 0

    conn.set_progress_handler(progress_handler, 1000)
    try:
        cur = conn.execute(sql)
        rows = cur.fetchmany(row_cap + 1)
        truncated = len(rows) > row_cap
        if truncated:
            rows = rows[:row_cap]
        columns = [d[0] for d in cur.description] if cur.description else []
        return {
            "ok": True,
            "error": None,
            "columns": columns,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
        }
    except sqlite3.OperationalError as e:
        if "interrupt" in str(e).lower():
            error = f"query timed out after {timeout_seconds}s"
        else:
            error = str(e)
        return {"ok": False, "error": error, "columns": [], "rows": [], "row_count": 0, "truncated": False}
    except sqlite3.Error as e:
        return {"ok": False, "error": str(e), "columns": [], "rows": [], "row_count": 0, "truncated": False}
    finally:
        conn.set_progress_handler(None, 0)
