# app/sessions/store.py
from datetime import datetime
from typing import Optional, List, Tuple, Any, Dict
from app.db.connector import get_conn

def _column_exists(cursor, table: str, column: str) -> bool:
    rows = cursor.execute(f"PRAGMA table_info({table})").fetchall()
    cols = {r[1] for r in rows}  # (cid, name, type, ...)
    return column in cols

def ensure_tables():
    with get_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS Sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS SessionTurns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                mode TEXT,
                question TEXT,
                clarified_question TEXT,
                sql TEXT,
                row_count INTEGER,
                chart_type TEXT,
                FOREIGN KEY(session_id) REFERENCES Sessions(id) ON DELETE CASCADE
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS AppFeedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_id INTEGER,
                vote TEXT,
                comment TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(turn_id) REFERENCES SessionTurns(id) ON DELETE CASCADE
            );
        """)
        # ---- Safe migrations for older DBs ----
        # Ensure AppFeedback.turn_id exists
        if not _column_exists(c, "AppFeedback", "turn_id"):
            c.execute("ALTER TABLE AppFeedback ADD COLUMN turn_id INTEGER")
        if not _column_exists(c, "AppFeedback", "created_at"):
            c.execute("ALTER TABLE AppFeedback ADD COLUMN created_at TEXT")

def list_sessions() -> List[Tuple[int, str]]:
    with get_conn() as c:
        rows = c.execute("SELECT id, name FROM Sessions ORDER BY created_at DESC").fetchall()
        return [(r[0], r[1]) for r in rows]

def get_session_id_by_name(name: str) -> Optional[int]:
    with get_conn() as c:
        r = c.execute("SELECT id FROM Sessions WHERE name = ?", (name,)).fetchone()
        return r[0] if r else None

def create_session(name: str) -> int:
    with get_conn() as c:
        now = datetime.utcnow().isoformat()+"Z"
        c.execute("INSERT INTO Sessions (name, created_at) VALUES (?, ?)", (name, now))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]

def get_or_create_session(name: str) -> int:
    sid = get_session_id_by_name(name)
    if sid is not None:
        return sid
    return create_session(name)

def rename_session(session_id: int, new_name: str) -> None:
    with get_conn() as c:
        c.execute("UPDATE Sessions SET name = ? WHERE id = ?", (new_name, session_id))

def delete_session(session_id: int) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM Sessions WHERE id = ?", (session_id,))

def save_turn(session_id: int, *, mode: str, question: Optional[str],
              clarified_question: Optional[str], sql: Optional[str],
              row_count: Optional[int], chart_type: Optional[str]) -> int:
    with get_conn() as c:
        now = datetime.utcnow().isoformat()+"Z"
        c.execute("""
            INSERT INTO SessionTurns (session_id, created_at, mode, question, clarified_question, sql, row_count, chart_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, now, mode, question, clarified_question, sql, row_count, chart_type))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]

def list_turns(session_id: int) -> List[Dict[str, Any]]:
    with get_conn() as c:
        rows = c.execute("""
            SELECT id, created_at, mode, question, clarified_question, sql, row_count, chart_type
            FROM SessionTurns WHERE session_id = ? ORDER BY id DESC
        """, (session_id,)).fetchall()
    cols = ["id","created_at","mode","question","clarified_question","sql","row_count","chart_type"]
    return [dict(zip(cols, r)) for r in rows]

def save_feedback_for_turn(turn_id: int, vote: str, comment: Optional[str]) -> int:
    with get_conn() as c:
        now = datetime.utcnow().isoformat()+"Z"
        c.execute("""
            INSERT INTO AppFeedback (turn_id, vote, comment, created_at)
            VALUES (?, ?, ?, ?)
        """, (turn_id, vote, comment, now))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]
