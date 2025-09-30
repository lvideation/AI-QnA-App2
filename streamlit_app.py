import os
from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st
from app.db.connector import get_conn, DB_PATH
from app.db.schema import get_schema_snapshot
from app.llm.router import generate_sql_from_nl, clarify_question

st.set_page_config(page_title="AI-QnA CRM Explorer", layout="wide")

st.markdown(
    """
    <style>
      * { font-family: Arial, sans-serif !important; }
      .block-container { padding: 0.75rem 1.5rem; }
      header[data-testid="stHeader"] { height: 0; }
      #MainMenu, footer { visibility: hidden; }
      .stTextArea textarea, .stTextInput input, .stSelectbox div { font-size:14px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

def list_tables(conn):
    q = """
    SELECT name FROM sqlite_master
    WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'
    ORDER BY name;
    """
    return [r[0] for r in conn.execute(q).fetchall()]

def head_table(conn, table, limit=50):
    return pd.read_sql_query(f"SELECT * FROM [{table}] LIMIT {int(limit)};", conn)

def run_readonly_sql(conn, sql, limit=1000):
    sql = sql.strip().rstrip(";")
    bad = ("insert ","update ","delete ","drop ","alter ","create ","truncate ",
           "replace ","attach ","pragma ","vacuum ","reindex ")
    low = sql.lower()
    if not low.startswith("select") or any(tok in low for tok in bad):
        raise ValueError("Only read-only SELECT queries are allowed.")
    if " limit " not in low:
        sql += f" LIMIT {int(limit)}"
    return pd.read_sql_query(sql, conn)

def suggest_visual(df: pd.DataFrame):
    if df.empty or df.shape[1] == 0:
        return None, (None, None), df
    num = df.select_dtypes(include="number").columns.tolist()
    dt  = df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns.tolist()
    cat = [c for c in df.columns if c not in num + dt]
    for c in df.columns:
        if df[c].dtype == "object":
            try:
                parsed = pd.to_datetime(df[c])
                if parsed.notna().sum() >= max(3, int(.2*len(parsed))):
                    df[c] = parsed
                    if c not in dt: dt.append(c)
            except Exception:
                pass
    if dt and num:         return "line",    (dt[0], num[0]), df
    if cat and num:        return "bar",     (cat[0], num[0]), df.groupby(cat[0], dropna=False, as_index=False)[num[0]].sum()
    if len(num) >= 2:      return "scatter", (num[0], num[1]), df
    if len(num) == 1:      return "hist",    (None,    num[0]), df
    return None, (None, None), df

def ensure_feedback_table():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS AppFeedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                session_name TEXT,
                mode TEXT,
                selected_table TEXT,
                query_sql TEXT,
                chart_type TEXT,
                vote TEXT,
                comment TEXT
            );
        """)

def save_feedback(session_name, mode, table, query_sql, chart_type, vote, comment):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO AppFeedback (created_at, session_name, mode, selected_table, query_sql, chart_type, vote, comment) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat()+"Z", session_name, mode, table, query_sql, chart_type, vote, comment)
        )

with get_conn() as _c:
    tables = list_tables(_c)

with st.sidebar:
    st.caption(f"DB: {Path(str(DB_PATH)).name if DB_PATH else 'not set'}")
    mode = st.radio("", ["Browse", "SQL", "NL Query"], label_visibility="collapsed")
    table = st.selectbox("", tables, label_visibility="collapsed") if (mode=="Browse" and tables) else None

ensure_feedback_table()
if "session_name" not in st.session_state:
    st.session_state.session_name = ""
colL, colM, colR = st.columns([6,2,2])
with colL:
    st.text_input("Session", key="session_name", placeholder="Name this session…", label_visibility="collapsed")
with colR:
    c1, c2, c3 = st.columns([1,1,3])
    up = c1.button("👍")
    down = c2.button("👎")
    fb_note = c3.text_input("Feedback (optional)", label_visibility="collapsed", placeholder="Add a note…")

st.title("CRM Explorer")

query_sql_for_log = None
chart_for_log = None

with get_conn() as conn:
    if mode == "Browse":
        if not tables:
            st.info("No tables found.")
        else:
            limit = st.slider("Rows to preview", 10, 200, 50)
            df = head_table(conn, table, limit)
            st.subheader(f"{table} · {len(df)} rows")
            st.dataframe(df, use_container_width=True)
            st.markdown("**Suggested visualization**")
            chart, (x, y), df2 = suggest_visual(df.copy())
            chart_for_log = chart
            if chart == "line":
                st.line_chart(df2.set_index(x)[[y]])
            elif chart == "bar":
                st.bar_chart(df2.set_index(x)[[y]])
            elif chart == "scatter":
                st.scatter_chart(df2[[x, y]].rename(columns={x:"x", y:"y"}))
            elif chart == "hist":
                st.bar_chart(df2[[y]])
            else:
                st.info("No obvious chart for these columns.")

    elif mode == "SQL":
        st.write("Enter a read-only SQL query (SELECT …). A LIMIT is added if missing.")
        sql = st.text_area("SQL", value="SELECT * FROM Account", height=140, label_visibility="collapsed")
        c1, c2 = st.columns([1,4])
        with c2:
            limit = st.slider("Max rows", 50, 5000, 1000)
        if c1.button("Run"):
            try:
                df = run_readonly_sql(conn, sql, limit=limit)
                query_sql_for_log = sql
                st.success(f"Returned {len(df)} rows")
                st.dataframe(df, use_container_width=True)
                st.markdown("**Suggested visualization**")
                chart, (x, y), df2 = suggest_visual(df.copy())
                chart_for_log = chart
                if chart == "line":
                    st.line_chart(df2.set_index(x)[[y]])
                elif chart == "bar":
                    st.bar_chart(df2.set_index(x)[[y]])
                elif chart == "scatter":
                    st.scatter_chart(df2[[x, y]].rename(columns={x:"x", y:"y"}))
                elif chart == "hist":
                    st.bar_chart(df2[[y]])
                else:
                    st.info("No obvious chart for these results.")
            except Exception as e:
                st.error(str(e))

    elif mode == "NL Query":
        st.write("Ask a question in natural language. **Clarify** first (optional), then **Generate SQL** and run.")
        if "nl_question" not in st.session_state:
            st.session_state.nl_question = "Top open opportunities by value with account and AE"

        st.text_area("Question", key="nl_question", height=120, label_visibility="collapsed")

        c1, c2, c3 = st.columns([1,1,4])
        with c3:
            limit = st.slider("Max rows", 50, 5000, 1000)

        clarify = c1.button("Clarify")
        generate = c2.button("Generate SQL")

        if clarify:
            with st.spinner("Proposing a clearer phrasing…"):
                try:
                    schema_hint = ", ".join(tables[:10]) if tables else ""
                    suggestion = clarify_question(st.session_state.nl_question.strip(), schema_hint=schema_hint)
                    st.session_state.nl_question = suggestion or st.session_state.nl_question
                    st.success("Updated the question. Review/edit if needed, then Generate SQL.")
                except Exception as e:
                    st.error(str(e))

        if generate:
            with st.spinner("Generating SQL…"):
                try:
                    schema_text = get_schema_snapshot()
                    sql = generate_sql_from_nl(st.session_state.nl_question.strip(), schema_text)
                    st.code(sql, language="sql")
                    if st.button("Run this query"):
                        try:
                            df = run_readonly_sql(conn, sql, limit=limit)
                            query_sql_for_log = sql
                            st.success(f"Returned {len(df)} rows")
                            st.dataframe(df, use_container_width=True)
                            st.markdown("**Suggested visualization**")
                            chart, (x, y), df2 = suggest_visual(df.copy())
                            chart_for_log = chart
                            if chart == "line":
                                st.line_chart(df2.set_index(x)[[y]])
                            elif chart == "bar":
                                st.bar_chart(df2.set_index(x)[[y]])
                            elif chart == "scatter":
                                st.scatter_chart(df2[[x, y]].rename(columns={x:"x", y:"y"}))
                            elif chart == "hist":
                                st.bar_chart(df2[[y]])
                            else:
                                st.info("No obvious chart for these results.")
                        except Exception as e:
                            st.error(str(e))
                except Exception as e:
                    st.error(str(e))

def _save(vote):
    try:
        save_feedback(
            session_name=st.session_state.session_name or None,
            mode=mode,
            selected_table=table if mode=="Browse" else None,
            query_sql=query_sql_for_log,
            chart_type=chart_for_log,
            vote=vote,
            comment=fb_note or None
        )
        st.toast(f"Thanks for the feedback ({vote}).")
    except Exception as e:
        st.error(f"Could not save feedback: {e}")

if 'up' in locals() and up:   _save("up")
if 'down' in locals() and down: _save("down")
