# app/llm/router.py
import os
import re
from typing import Optional
from app.llm.domain import DOMAIN_CONTEXT

def _is_read_only(sql: str) -> bool:
    s = sql.strip().lower()
    forbidden = (
        "insert ", "update ", "delete ", "drop ", "alter ", "create ",
        "truncate ", "replace ", "attach ", "pragma ", "vacuum ", "reindex "
    )
    return s.startswith("select") and not any(tok in s for tok in forbidden)

def _ensure_limit(sql: str, default_limit: int = 1000) -> str:
    if not re.search(r"\blimit\s+\d+\b", sql, flags=re.IGNORECASE):
        sql = f"{sql} LIMIT {int(default_limit)}"
    return sql

def _strip_fences(s: str) -> str:
    return re.sub(r"^```[a-zA-Z]*|```$", "", s, flags=re.MULTILINE).strip().rstrip(";")

def _use_openai():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
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
        + "\n\nYou are a helpful product analyst. Rewrite the user's question into a clearer, "
          "crisper single sentence suitable for converting to SQL. Do not change the meaning or invent fields."
    )
    user = (
        nl_question
        if not schema_hint
        else f"Schema hint:\n{schema_hint}\n\nQuestion:\n{nl_question}\n\nRewrite clearly:"
    )

    ol = _use_ollama()
    if ol:
        try:
            model = os.getenv("OLLAMA_MODEL", "llama3:8b")
            r = ol.chat(
                model=model,
                messages=[{"role": "user", "content": f"{system}\n\n{user}"}],
                options={"temperature": 0.2}
            )
            return r["message"]["content"].strip().strip('"')
        except Exception:
            pass

    client = _use_openai()
    if client:
        try:
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0.2,
                max_tokens=120
            )
            return resp.choices[0].message.content.strip().strip('"')
        except Exception:
            pass

    return nl_question.strip()

def generate_sql_from_nl(nl_question: str, schema_snapshot: str) -> str:
    system = (
        DOMAIN_CONTEXT
        + "\n\nYou are a senior data analyst. Generate ONE SQLite SELECT query.\n"
          "Rules: SELECT-only; no PRAGMA/DDL/DML; no comments or code fences; no trailing semicolon.\n"
          "Use only columns/tables that exist in the provided schema. Prefer explicit JOINs."
    )
    user = (
        f"Schema:\n{schema_snapshot}\n\n"
        f"Question: {nl_question}\n\n"
        f"Return ONLY the SQL."
    )

    ol = _use_ollama()
    if ol:
        try:
            model = os.getenv("OLLAMA_MODEL", "llama3:8b")
            r = ol.chat(
                model=model,
                messages=[{"role": "user", "content": system + "\n\n" + user}],
                options={"temperature": 0.1}
            )
            sql = _strip_fences(r["message"]["content"])
            if not _is_read_only(sql):
                raise ValueError("Model returned non read-only SQL")
            return _ensure_limit(sql)
        except Exception:
            pass

    client = _use_openai()
    if client:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.1,
            max_tokens=300
        )
        sql = _strip_fences(resp.choices[0].message.content)
        if not _is_read_only(sql):
            raise ValueError("Model returned non read-only SQL")
        return _ensure_limit(sql)

    raise RuntimeError("No LLM available (Ollama/OpenAI)")

def repair_sql_with_error(nl_question: str, schema_snapshot: str, bad_sql: str, error_msg: str) -> Optional[str]:
    system = (
        DOMAIN_CONTEXT
        + "\n\nYou are a SQL repair assistant. Fix the user's SQL for SQLite with the given schema and error. "
          "Return ONLY a corrected SELECT query (no comments/fences/semicolon). Keep the same intent."
    )
    user = (
        f"Schema:\n{schema_snapshot}\n\n"
        f"Question:\n{nl_question}\n\n"
        f"Previous SQL:\n{bad_sql}\n\n"
        f"SQLite error:\n{error_msg}\n\n"
        f"Return corrected SQL only."
    )

    ol = _use_ollama()
    if ol:
        try:
            model = os.getenv("OLLAMA_MODEL", "llama3:8b")
            r = ol.chat(
                model=model,
                messages=[{"role": "user", "content": system + "\n\n" + user}],
                options={"temperature": 0.0}
            )
            sql = _strip_fences(r["message"]["content"])
            if not _is_read_only(sql):
                return None
            return _ensure_limit(sql)
        except Exception:
            pass

    client = _use_openai()
    if client:
        try:
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0.0,
                max_tokens=300
            )
            sql = _strip_fences(resp.choices[0].message.content)
            if not _is_read_only(sql):
                return None
            return _ensure_limit(sql)
        except Exception:
            return None

    return None
