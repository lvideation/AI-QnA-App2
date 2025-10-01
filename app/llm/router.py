# app/llm/router.py
import os, re
from typing import Optional
from app.llm.domain import DOMAIN_CONTEXT

def _is_read_only(sql: str) -> bool:
    s = sql.strip().lower()
    forbidden = ("insert ","update ","delete ","drop ","alter ","create ",
                 "truncate ","replace ","attach ","pragma ","vacuum ","reindex ")
    return s.startswith("select") and not any(tok in s for tok in forbidden)

def _ensure_limit(sql: str, default_limit: int = 1000) -> str:
    if not re.search(r"\blimit\s+\d+\b", sql, flags=re.IGNORECASE):
        sql = f"{sql} LIMIT {int(default_limit)}"
    return sql

def _strip_fences(s: str) -> str:
    return re.sub(r"^```[a-zA-Z]*|```$", "", s, flags=re.MULTILINE).strip().rstrip(";")

def _normalize_sqlite(sql: str) -> str:
    s = sql.strip()
    # 1) SELECT TOP N ...  ->  SELECT ... LIMIT N
    m = re.match(r"(?is)^\s*select\s+top\s+(\d+)\s+(.*)$", s)
    if m:
        n, rest = m.group(1), m.group(2)
        s = f"SELECT {rest}"
        # append LIMIT only if not present
        if not re.search(r"\blimit\s+\d+\b", s, flags=re.IGNORECASE):
            s = f"{s} LIMIT {n}"
    # 2) ILIKE -> LIKE (SQLite lacks ILIKE)
    s = re.sub(r"\bILIKE\b", "LIKE", s, flags=re.IGNORECASE)
    # 3) TRUE/FALSE -> 1/0
    s = re.sub(r"\bTRUE\b", "1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bFALSE\b", "0", s, flags=re.IGNORECASE)
    # 4) De-duplicate LIMIT (keep the first one found)
    limits = list(re.finditer(r"\blimit\s+\d+\b", s, flags=re.IGNORECASE))
    if len(limits) > 1:
        # remove all but the first
        first = limits[0]
        s_wo = re.sub(r"\blimit\s+\d+\b", "", s, flags=re.IGNORECASE)
        # then insert the first LIMIT at the end
        first_num = re.search(r"\d+", first.group(0)).group(0)
        s = re.sub(r";\s*$", "", s_wo).strip()
        if not re.search(r"\blimit\s+\d+\b", s, flags=re.IGNORECASE):
            s = f"{s} LIMIT {first_num}"
    return s

def _use_openai():
    key = os.getenv("OPENAI_API_KEY")
    if not key: return None
    from openai import OpenAI
    return OpenAI(api_key=key)

def _use_ollama():
    try:
        import ollama
        return ollama
    except Exception:
        return None

def clarify_question(nl_question: str, schema_hint: Optional[str] = None) -> str:
    system = (
        DOMAIN_CONTEXT
        + "\n\nYou are a helpful product analyst. Rewrite the user's question into a clearer single sentence. "
          "Do not change meaning or invent fields. Keep CRM semantics: Opportunity ≠ Engagement."
    )
    user = nl_question if not schema_hint else f"Schema hint:\n{schema_hint}\n\nQuestion:\n{nl_question}\n\nRewrite clearly:"

    ol = _use_ollama()
    if ol:
        try:
            model = os.getenv("OLLAMA_MODEL", "llama3:8b")
            r = ol.chat(model=model, messages=[{"role":"user","content": f"{system}\n\n{user}"}], options={"temperature":0.2})
            return r["message"]["content"].strip().strip('"')
        except Exception:
            pass

    client = _use_openai()
    if client:
        try:
            model = os.getenv("OPENAI_MODEL","gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role":"system","content":system},
                          {"role":"user","content":user}],
                temperature=0.2, max_tokens=120
            )
            return resp.choices[0].message.content.strip().strip('"')
        except Exception:
            pass
    return nl_question.strip()

def generate_sql_from_nl(nl_question: str, schema_snapshot: str) -> str:
    system = (
        DOMAIN_CONTEXT
        + "\n\nYou are a senior data analyst. Generate ONE **SQLite** SELECT query only.\n"
          "- Use **LIMIT** (SQLite). **Never** use TOP, OFFSET without LIMIT, or vendor features.\n"
          "- If you order by `opportunity_value`, you **must** compute it as "
          "SUM(OpportunityProduct.product_qty * Product.product_price).\n"
          "- SELECT-only; no PRAGMA/DDL/DML; no comments or code fences; no trailing semicolon.\n"
          "- Use only provided schema tables/columns; explicit JOINs; clear aliases."
    )
    user = f"Schema:\n{schema_snapshot}\n\nQuestion: {nl_question}\n\nReturn ONLY the SQL."

    ol = _use_ollama()
    if ol:
        try:
            model = os.getenv("OLLAMA_MODEL","llama3:8b")
            r = ol.chat(model=model, messages=[{"role":"user","content": system+"\n\n"+user}], options={"temperature":0.1})
            sql = _strip_fences(r["message"]["content"])
            sql = _normalize_sqlite(sql)
            if not _is_read_only(sql): raise ValueError("Model returned non read-only SQL")
            return _ensure_limit(sql)
        except Exception:
            pass

    client = _use_openai()
    if client:
        model = os.getenv("OPENAI_MODEL","gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content":system},
                      {"role":"user","content":user}],
            temperature=0.1, max_tokens=300
        )
        sql = _strip_fences(resp.choices[0].message.content)
        sql = _normalize_sqlite(sql)
        if not _is_read_only(sql): raise ValueError("Model returned non read-only SQL")
        return _ensure_limit(sql)
    raise RuntimeError("No LLM available (Ollama/OpenAI)")

def repair_sql_with_error(nl_question: str, schema_snapshot: str, bad_sql: str, error_msg: str) -> Optional[str]:
    # quick normalization pass first (e.g. fix TOP→LIMIT)
    norm = _normalize_sqlite(bad_sql)
    if norm != bad_sql and _is_read_only(norm):
        return _ensure_limit(norm)

    system = (
        DOMAIN_CONTEXT
        + "\n\nYou are a SQL repair assistant for **SQLite**. Fix the query given the schema and error. "
          "Rules: SELECT-only; no comments/fences/semicolon; use LIMIT; never use TOP."
    )
    user = (f"Schema:\n{schema_snapshot}\n\nQuestion:\n{nl_question}\n\n"
            f"Previous SQL:\n{bad_sql}\n\nSQLite error:\n{error_msg}\n\nReturn corrected SQL only.")

    ol = _use_ollama()
    if ol:
        try:
            model = os.getenv("OLLAMA_MODEL","llama3:8b")
            r = ol.chat(model=model, messages=[{"role":"user","content": system+"\n\n"+user}], options={"temperature":0.0})
            sql = _strip_fences(r["message"]["content"])
            sql = _normalize_sqlite(sql)
            if not _is_read_only(sql): return None
            return _ensure_limit(sql)
        except Exception:
            pass

    client = _use_openai()
    if client:
        try:
            model = os.getenv("OPENAI_MODEL","gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role":"system","content":system},
                          {"role":"user","content":user}],
                temperature=0.0, max_tokens=300
            )
            sql = _strip_fences(resp.choices[0].message.content)
            sql = _normalize_sqlite(sql)
            if not _is_read_only(sql): return None
            return _ensure_limit(sql)
        except Exception:
            return None
    return None
