# app/llm/router.py
import os
import re
from typing import Optional

def _is_read_only(sql: str) -> bool:
    s = sql.strip().lower()
    forbidden = ("insert ","update ","delete ","drop ","alter ","create ","truncate ",
                 "replace ","attach ","pragma ","vacuum ","reindex ")
    return s.startswith("select") and not any(tok in s for tok in forbidden)

def _use_openai():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=key)

def clarify_question(nl_question: str, schema_hint: Optional[str] = None) -> str:
    """
    Return a shorter, precise rewritten question (one sentence if possible).
    """
    system = (
        "You are a helpful product analyst. Rewrite the user's question "
        "into a clearer, crisper version suitable for converting to SQL. "
        "Keep ONE sentence if possible. Do not add fields not requested."
    )
    user = nl_question if not schema_hint else f"Schema hint:\n{schema_hint}\n\nQuestion:\n{nl_question}\n\nRewrite clearly:"

    client = _use_openai()
    if client:
        try:
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role":"system","content":system},
                          {"role":"user","content":user}],
                temperature=0.2,
                max_tokens=120
            )
            return resp.choices[0].message.content.strip().strip('"')
        except Exception:
            pass

    try:
        import ollama
        model = os.getenv("OLLAMA_MODEL", "llama3")
        prompt = f"{system}\n\n{user}"
        r = ollama.chat(model=model, messages=[{"role":"user","content":prompt}])
        return r["message"]["content"].strip().strip('"')
    except Exception:
        return nl_question.strip()

def generate_sql_from_nl(nl_question: str, schema_snapshot: str) -> str:
    """
    Generate a single SQLite SELECT (no ;), read-only, no code fences.
    """
    system = (
        "You are a senior data analyst. Generate a single SQLite SELECT query only.\n"
        "Rules: SELECT-only, no PRAGMA/DDL/DML, no comments, no ``` fences, no trailing semicolon.\n"
        "Prefer explicit JOINs. Use columns and tables from the schema below."
    )
    user = f"Schema:\n{schema_snapshot}\n\nQuestion: {nl_question}\n\nReturn only the SQL (no explanation)."

    client = _use_openai()
    if client:
        try:
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role":"system","content":system},
                          {"role":"user","content":user}],
                temperature=0.1,
                max_tokens=300
            )
            sql = resp.choices[0].message.content.strip()
            sql = re.sub(r"^```[a-zA-Z]*|```$", "", sql, flags=re.MULTILINE).strip()
            sql = sql.rstrip(";")
            if not _is_read_only(sql):
                raise ValueError("Model returned non read-only SQL")
            return sql
        except Exception:
            pass

    import ollama
    model = os.getenv("OLLAMA_MODEL", "llama3")
    prompt = system + "\n\n" + user
    r = ollama.chat(model=model, messages=[{"role":"user","content":prompt}])
    sql = r["message"]["content"].strip()
    sql = re.sub(r"^```[a-zA-Z]*|```$", "", sql, flags=re.MULTILINE).strip()
    sql = sql.rstrip(";")
    if not _is_read_only(sql):
        raise ValueError("Model returned non read-only SQL")
    return sql
