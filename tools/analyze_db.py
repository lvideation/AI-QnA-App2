#!/usr/bin/env python3
import sqlite3, json
from collections import defaultdict, deque
from pathlib import Path
from datetime import datetime

DB_PATH = Path("/Users/venky/AI-QnA-App2/data/crmB.db")
OUT_DIR = Path("/Users/venky/AI-QnA-App2/_reports")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def get_tables(conn):
    return conn.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%';"
    ).fetchall()

def get_columns(conn, table):
    return conn.execute(f"PRAGMA table_info('{table}')").fetchall()

def get_foreign_keys(conn, table):
    return conn.execute(f"PRAGMA foreign_key_list('{table}')").fetchall()

def topo_sort(fk_edges):
    indeg, nodes = defaultdict(int), set()
    for child, parents in fk_edges.items():
        nodes.add(child)
        for p in parents:
            nodes.add(p); indeg[child]+=1
    for n in list(nodes): indeg.setdefault(n,0)
    q, order = deque([n for n in nodes if indeg[n]==0]), []
    while q:
        n=q.popleft(); order.append(n)
        for c, ps in fk_edges.items():
            if n in ps:
                indeg[c]-=1
                if indeg[c]==0: q.append(c)
    return order

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON;")

    tables = get_tables(conn)
    fk_edges = defaultdict(set)
    schema = {"db": str(DB_PATH), "generated": datetime.utcnow().isoformat()+"Z", "tables":[]}

    for name, typ in tables:
        cols = get_columns(conn,name)
        fks  = get_foreign_keys(conn,name) if typ=="table" else []
        schema["tables"].append({"name":name,"type":typ,
            "columns":[dict(name=c[1],type=c[2],pk=bool(c[5])) for c in cols],
            "foreign_keys":[dict(ref_table=f[2],from_col=f[3],to_col=f[4]) for f in fks]
        })
        for f in fks: fk_edges[name].add(f[2])

    schema["load_order_hint"]=topo_sort(fk_edges)

    with (OUT_DIR/"schema.json").open("w") as f: json.dump(schema,f,indent=2)
    print("Wrote schema.json under",OUT_DIR)

if __name__=="__main__":
    main()
