import os
from pathlib import Path
import pandas as pd
import streamlit as st

from app.db.connector import get_conn, DB_PATH
from app.db.schema import get_schema_snapshot
from app.llm.router import generate_sql_from_nl, clarify_question, repair_sql_with_error
from app.brain.router import classify_intent
from app.sessions.store import (
    ensure_tables, get_or_create_session, list_sessions, rename_session,
    delete_session, save_turn, list_turns, save_feedback_for_turn
)
from app.external.company import fetch_sec_10k_items, fetch_news_snippets, summarize_10k_business_priorities

# ---------------- Page & global styles ----------------
st.set_page_config(page_title="AI-QnA — Unified Query", layout="wide")
st.markdown("""
<style>
  * { font-family: Arial, sans-serif !important; }
  .block-container { padding: 0.9rem 1.1rem; }
  header[data-testid="stHeader"] { height: 0; }
  #MainMenu, footer { visibility: hidden; }
  div.stButton>button { font-size:11px !important; padding:0.22rem 0.55rem; white-space: nowrap; }
  .pill { display:inline-block; padding:.2rem .5rem; border-radius:999px; font-size:12px; margin-left:.5rem; }
  .pill-db { background:#e6f2ff; color:#024; }
  .pill-10k { background:#eef7e9; color:#062; }
  .pill-news { background:#fff3e6; color:#640; }
  .pill-off { background:#f6e6ef; color:#602; }
  .suggestbox { background:#f7f7f7; border:1px solid #e5e5e5; padding:.6rem .7rem; border-radius:.6rem; }
</style>
""", unsafe_allow_html=True)

# ---------------- Ensure app tables & migrations ----------------
ensure_tables()

# ---------------- Helpers ----------------
def list_tables(conn):
    q = """
    SELECT name FROM sqlite_master
    WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'
    ORDER BY name;
    """
    return [r[0] for r in conn.execute(q).fetchall()]

def run_readonly_sql(conn, sql, limit=1000):
    s0 = sql.strip().rstrip(";")
    low = s0.lower()
    forbidden = ("insert ","update ","delete ","drop ","alter ","create ","truncate ",
                 "replace ","attach ","pragma ","vacuum ","reindex ")
    if not low.startswith("select") or any(tok in low for tok in forbidden):
        raise ValueError("Only read-only SELECT queries are allowed.")
    import re as _re
    if not _re.search(r"\blimit\s+\d+\b", s0, flags=_re.IGNORECASE):
        s0 = f"{s0} LIMIT {int(limit)}"
    return pd.read_sql_query(s0, conn)

def suggest_visual(df: pd.DataFrame):
    if df is None or df.empty or df.shape[1] == 0:
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

# ---------------- Sidebar: DB badge + simpler session save ----------------
with get_conn() as _c:
    _tables = list_tables(_c)

st.sidebar.caption(f"DB: {Path(str(DB_PATH)).name if DB_PATH else 'not set'}")

# Session controls: Name + Save/Load + Delete (simpler than old rename flow)
st.sidebar.markdown("**Session**")
sess_rows = list_sessions()
sess_names = [name for (_id, name) in sess_rows]
current = st.sidebar.selectbox("Load", options=["(none)"] + sess_names, index=0)

if "session_name" not in st.session_state:
    st.session_state.session_name = "" if current == "(none)" else current

sess_name_input = st.sidebar.text_input("Session name", value=st.session_state.session_name or "")
sc1, sc2, sc3 = st.sidebar.columns(3)
if sc1.button("Save"):
    name = (sess_name_input or "").strip()
    if not name:
        st.warning("Enter a session name before saving.")
    else:
        st.session_state.session_name = name
        get_or_create_session(name)
        st.success(f"Saved session: {name}")
if sc2.button("Load"):
    if current != "(none)":
        st.session_state.session_name = current
        st.success(f"Loaded session: {current}")
    else:
        st.info("Pick a session from the dropdown to load.")
if sc3.button("Delete"):
    if current != "(none)":
        sid = get_or_create_session(current)
        delete_session(sid)
        st.session_state.session_name = ""
        st.success("Session deleted.")
    else:
        st.info("Pick a session to delete.")

# ---------------- Center: single input + Clarify (no SQL shown) ----------------
st.title("Ask anything")
st.caption("I’ll decide: CRM DB, 10-K, or News. (Clarify proposes a rewrite; no SQL is shown.)")

if "user_q" not in st.session_state:
    st.session_state.user_q = "Show top open opportunities by value with account and AE"
if "suggested_q" not in st.session_state:
    st.session_state.suggested_q = None
if "gen_sql" not in st.session_state:
    st.session_state.gen_sql = None
if "last_turn_id" not in st.session_state:
    st.session_state.last_turn_id = None

# Apply pending rewrite BEFORE rendering the text widget
if "pending_user_q" in st.session_state:
    st.session_state.user_q = st.session_state.pop("pending_user_q")

st.text_area("Your message", key="user_q", height=110, label_visibility="collapsed")

row1 = st.columns([1,1,3,3])
clar = row1[0].button("Clarify")
go   = row1[1].button("Go")
with row1[2]:
    limit = st.slider("Max rows (for tables)", 50, 5000, 1000)
with row1[3]:
    route_override = st.selectbox("Route (auto or force)", ["Auto", "CRM DB", "10-K", "News"], index=0)

# Clarify first
if clar:
    try:
        schema_hint = ", ".join(_tables[:10]) if _tables else ""
        suggestion = clarify_question(st.session_state.user_q.strip(), schema_hint=schema_hint)
        st.session_state.suggested_q = suggestion or st.session_state.user_q
        st.success("Proposed a clearer phrasing below.")
    except Exception as e:
        st.error(str(e))

# Show the proposed rewrite with Use/Keep
if st.session_state.suggested_q:
    st.markdown("**Proposed rewrite:**")
    st.markdown(f"<div class='suggestbox'>{st.session_state.suggested_q}</div>", unsafe_allow_html=True)
    ac1, ac2 = st.columns(2)
    if ac1.button("Use suggestion"):
        st.session_state["pending_user_q"] = st.session_state.suggested_q
        st.session_state.suggested_q = None
        st.rerun()
    if ac2.button("Keep original"):
        st.session_state.suggested_q = None
        st.rerun()

# ---------------- Go: classify (or override) and fulfill ----------------
if go:
    original_q = st.session_state.user_q.strip()
    # Auto-use Clarify for this run (even if user didn't click "Use suggestion")
    effective_q = (st.session_state.suggested_q or original_q).strip()

    if not effective_q:
        st.warning("Please type a question.")
    else:
        # Route override (if user forces it)
        if route_override == "CRM DB":
            route = "crm_db"
        elif route_override == "10-K":
            route = "external_10k"
        elif route_override == "News":
            route = "external_news"
        else:
            route = classify_intent(effective_q)

        pill = {"crm_db":"pill-db","external_10k":"pill-10k","external_news":"pill-news","offtopic":"pill-off"}[route]
        st.markdown(f"**Route:** <span class='pill {pill}'>{route}</span>", unsafe_allow_html=True)
        st.session_state.last_turn_id = None

        if route == "crm_db":
            try:
                schema_text = get_schema_snapshot()
                sql = generate_sql_from_nl(effective_q, schema_text)
                with get_conn() as conn:
                    try:
                        df = run_readonly_sql(conn, sql, limit=limit)
                    except Exception as e1:
                        fixed = repair_sql_with_error(effective_q, schema_text, sql, str(e1))
                        if not fixed:
                            raise
                        df = run_readonly_sql(conn, fixed, limit=limit)
                        sql = fixed
                st.success(f"Returned {len(df)} rows")
                st.dataframe(df, use_container_width=True)

                try:
                    chart, (x, y), df2 = suggest_visual(df.copy())
                except Exception:
                    chart, (x, y), df2 = (None, (None, None), df)

                if chart == "line" and x and y:
                    st.line_chart(df2.set_index(x)[[y]])
                elif chart == "bar" and x and y:
                    st.bar_chart(df2.set_index(x)[[y]])
                elif chart == "scatter" and x and y:
                    st.scatter_chart(df2[[x, y]].rename(columns={x: "x", y: "y"}))
                elif chart == "hist" and y:
                    st.bar_chart(df2[[y]])
                else:
                    st.info("No obvious chart for these results.")

                if st.session_state.get("session_name"):
                    sid = get_or_create_session(st.session_state["session_name"])
                    st.session_state.last_turn_id = save_turn(
                        session_id=sid,
                        mode="NL-DB",
                        question=original_q,
                        clarified_question=(st.session_state.suggested_q or None),
                        sql=None,
                        row_count=int(len(df)),
                        chart_type=chart
                    )
            except Exception as e:
                st.error(f"Couldn’t complete the DB query. Try rephrasing or hit Clarify. Details: {e}")

        elif route == "external_10k":
            items = fetch_sec_10k_items(effective_q, max_items=5)
            st.subheader("10-K filings")
            if items:
                st.dataframe(pd.DataFrame(items), use_container_width=True)
                # Summarize business priorities from the most recent filing
                summary = summarize_10k_business_priorities(items[0]["url"])
                if summary:
                    st.markdown("#### Business Priorities (10-K)")
                    st.markdown(summary)
                else:
                    st.info("Couldn’t summarize priorities (network/parse limits). You can open the filing link above.")
            else:
                tips = []
                if not os.getenv("SEC_EMAIL"):
                    tips.append("Set SEC_EMAIL in your .env (used in SEC User-Agent).")
                tips.append("Try a precise company or ticker (e.g., AAPL, MSFT).")
                tips.append("Include '10-K' or 'annual report' in your question, or force the route in the dropdown.")
                st.info("No 10-K results.\n\n- " + "\n- ".join(tips))
            if st.session_state.get("session_name"):
                sid = get_or_create_session(st.session_state["session_name"])
                st.session_state.last_turn_id = save_turn(
                    session_id=sid, mode="EXT-10K", question=original_q,
                    clarified_question=(st.session_state.suggested_q or None),
                    sql=None, row_count=None, chart_type=None
                )

        elif route == "external_news":
            news = fetch_news_snippets(effective_q, max_items=5)  # limit to TOP 5
            st.subheader("Recent news (top 5)")
            if news:
                st.dataframe(pd.DataFrame(news), use_container_width=True)
            else:
                st.info("No news found. Try a company/ticker (e.g., 'NVIDIA news'), or force 'News' via the dropdown.")
            if st.session_state.get("session_name"):
                sid = get_or_create_session(st.session_state["session_name"])
                st.session_state.last_turn_id = save_turn(
                    session_id=sid, mode="EXT-NEWS", question=original_q,
                    clarified_question=(st.session_state.suggested_q or None),
                    sql=None, row_count=None, chart_type=None
                )

        else:
            st.warning("This looks outside CRM or company intel. Please rephrase or ask about CRM metrics, 10-K items, or recent news.")
            if st.session_state.get("session_name"):
                sid = get_or_create_session(st.session_state["session_name"])
                st.session_state.last_turn_id = save_turn(
                    session_id=sid, mode="OFFTOPIC", question=original_q,
                    clarified_question=(st.session_state.suggested_q or None),
                    sql=None, row_count=None, chart_type=None
                )

# ---------------- Feedback (compact) ----------------
if st.session_state.get("last_turn_id"):
    st.markdown("<p style='font-size:14px; margin-bottom:4px;'>Was this answer useful?</p>", unsafe_allow_html=True)
    fb1, fb2 = st.columns(2)
    note = st.text_input("Optional comment", label_visibility="collapsed", placeholder="Tell us why…")
    if fb1.button("👍"):
        save_feedback_for_turn(st.session_state["last_turn_id"], "up", note or None)
        st.success("Thanks for the feedback!")
    if fb2.button("👎"):
        save_feedback_for_turn(st.session_state["last_turn_id"], "down", note or None)
        st.info("Feedback saved.")

# ---------------- Recent turns ----------------
if st.session_state.get("session_name"):
    try:
        sid = get_or_create_session(st.session_state["session_name"])
        turns = list_turns(sid)[:10]
        if turns:
            st.markdown("### Recent turns")
            st.dataframe(pd.DataFrame(turns), use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load recent turns: {e}")
