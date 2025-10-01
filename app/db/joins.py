# app/db/joins.py
from typing import List, Dict, Tuple, Optional
from app.db.connector import get_conn

def get_foreign_keys() -> Dict[str, List[Tuple[str, str, str]]]:
    """
    Returns: {table: [(fk_from_col, ref_table, ref_col), ...]}
    Uses PRAGMA foreign_key_list to read actual relationships.
    """
    fks: Dict[str, List[Tuple[str, str, str]]] = {}
    with get_conn() as c:
        tables = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()]
        for t in tables:
            rows = c.execute(f"PRAGMA foreign_key_list('{t}')").fetchall()
            fks[t] = [(r[3], r[2], r[4]) for r in rows]  # (from_col, ref_table, ref_col)
    return fks

def suggest_join_plan(tables: List[str]) -> List[Tuple[str, str, str, str]]:
    """
    Given a list of tables, auto-suggest LEFT JOIN plan using discovered FKs.
    Returns: list of join steps as (left_table, left_col, right_table, right_col).
    Strategy: pick the first as root; try to link each remaining table via any FK edge.
    """
    if not tables:
        return []
    fks = get_foreign_keys()
    remaining = set(tables[1:])
    plan: List[Tuple[str, str, str, str]] = []
    connected = {tables[0]}

    # Build undirected edges for search
    edges = []  # (t1, c1, t2, c2) both directions
    for t, triplets in fks.items():
        for (from_col, ref_table, ref_col) in triplets:
            edges.append((t, from_col, ref_table, ref_col))
            edges.append((ref_table, ref_col, t, from_col))

    # Greedy connect
    while remaining:
        progress = False
        for rt in list(remaining):
            found_edge = None
            for (t1, c1, t2, c2) in edges:
                if rt == t1 and t2 in connected:
                    found_edge = (t2, c2, t1, c1)  # connect rt to connected t2
                    break
                if rt == t2 and t1 in connected:
                    found_edge = (t1, c1, t2, c2)
                    break
            if found_edge:
                plan.append(found_edge)  # (left_table, left_col, right_table, right_col)
                connected.add(rt)
                remaining.remove(rt)
                progress = True
        if not progress:
            # Could not auto-connect some; stop (user can override in UI)
            break
    return plan

def build_flatten_sql(tables: List[str], joins: List[Tuple[str, str, str, str]], limit: int = 200) -> str:
    """
    Build a SELECT with LEFT JOINs using the provided join plan.
    Qualifies columns to avoid name collisions: table_column aliases.
    """
    if not tables:
        return "SELECT 1 WHERE 0"
    root = tables[0]
    select_cols = []
    with get_conn() as c:
        # Columns from each table
        for t in tables:
            cols = [r[1] for r in c.execute(f"PRAGMA table_info('{t}')").fetchall()]
            for col in cols:
                alias = f"{t}_{col}"
                select_cols.append(f"[{t}].[{col}] AS [{alias}]")
    sql = f"SELECT {', '.join(select_cols)} FROM [{root}]"
    for (lt, lc, rt, rc) in joins:
        sql += f" LEFT JOIN [{rt}] ON [{lt}].[{lc}] = [{rt}].[{rc}]"
    sql += f" LIMIT {int(limit)}"
    return sql
