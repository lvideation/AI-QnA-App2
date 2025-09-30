# app/db/schema.py
from app.db.connector import get_conn

def get_schema_snapshot(max_cols_per_table: int = 20) -> str:
    """
    Returns a compact textual schema: tables + columns + FK hints.
    """
    with get_conn() as conn:
        tables = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()
        out = []
        for (t,) in tables:
            cols = conn.execute(f"PRAGMA table_info('{t}')").fetchall()
            col_list = ", ".join([c[1] for c in cols][:max_cols_per_table])
            out.append(f"- {t}({col_list})")
        fks = []
        for (t,) in tables:
            for fk in conn.execute(f"PRAGMA foreign_key_list('{t}')").fetchall():
                # fk = (id, seq, table, from, to, on_update, on_delete, match)
                fks.append(f"{t}.{fk[3]} -> {fk[2]}.{fk[4]}")
        if fks:
            out.append("\nForeign keys:")
            out.extend([f"  - {x}" for x in fks])
        return "\n".join(out)
