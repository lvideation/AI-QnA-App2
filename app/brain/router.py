# app/brain/router.py
import os
from typing import Literal

Intent = Literal["crm_db", "external_10k", "external_news", "offtopic"]

NEWS_WORDS = [
    "news","headline","headlines","press","press release","article","coverage",
    "latest","recent","what's new","update","updates","today","breaking"
]
K10K_WORDS = [
    "10k","10-k","annual report","form 10-k","risk factors","md&a","management discussion",
    "sec filing","sec filings","filing","filings"
]

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

def classify_intent(question: str) -> Intent:
    q = (question or "").strip().lower()

    # strong heuristics first (so you get News/10-K reliably)
    if any(w in q for w in K10K_WORDS):
        return "external_10k"
    if any(w in q for w in NEWS_WORDS):
        return "external_news"

    # Ollama
    ol = _use_ollama()
    if ol:
        try:
            model = os.getenv("OLLAMA_MODEL","llama3:8b")
            sys = ("Classify the user's request into exactly one of: "
                   "crm_db | external_10k | external_news | offtopic. Reply with ONLY the label.")
            r = ol.chat(model=model, messages=[{"role":"user","content": f"{sys}\n\n{q}"}], options={"temperature":0})
            label = r["message"]["content"].strip().lower()
            if label in ("crm_db","external_10k","external_news","offtopic"):
                return label  # type: ignore
        except Exception:
            pass

    # OpenAI
    client = _use_openai()
    if client:
        try:
            model = os.getenv("OPENAI_MODEL","gpt-4o-mini")
            sys = ("Classify the user's request into exactly one of: "
                   "crm_db | external_10k | external_news | offtopic. Reply with ONLY the label.")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role":"system","content":sys},{"role":"user","content":q}],
                temperature=0
            )
            label = resp.choices[0].message.content.strip().lower()
            if label in ("crm_db","external_10k","external_news","offtopic"):
                return label  # type: ignore
        except Exception:
            pass

    # default: CRM DB
    return "crm_db"
