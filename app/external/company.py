# app/external/company.py
import os, re
from typing import Dict, Any, List, Optional
from urllib.parse import quote_plus

USER_AGENT = os.getenv("SEC_EMAIL") or "AI-QnA-App2 (set SEC_EMAIL in .env)"

def _req_json(url: str) -> Optional[dict]:
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None

def _req_text(url: str) -> Optional[str]:
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if r.status_code == 200:
            return r.text
    except Exception:
        return None
    return None

def _load_tickers_map() -> Dict[str, Dict[str, Any]]:
    j = _req_json("https://www.sec.gov/files/company_tickers.json")
    return j or {}

def _match_cik_for_query(q: str) -> Optional[str]:
    data = _load_tickers_map()
    if not data: return None
    ql = q.strip().lower()
    for _, row in data.items():
        if row.get("ticker","").lower() == ql:
            return f'{int(row["cik_str"]):010d}'
    for _, row in data.items():
        name = row.get("title","").lower()
        if ql in name:
            return f'{int(row["cik_str"]):010d}'
    return None

def fetch_sec_10k_items(company_or_ticker: str, max_items: int = 5) -> List[Dict[str, Any]]:
    cik = _match_cik_for_query(company_or_ticker)
    if not cik:
        return []
    sub = _req_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    if not sub: return []
    forms = sub.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(forms.get("form", [])):
        if str(form).lower() == "10-k":
            date = forms.get("filingDate", [""])[i]
            accn = forms.get("accessionNumber", [""])[i]
            primary = forms.get("primaryDocument", [""])[i]
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-','')}/{primary}"
            out.append({"filing_date": date, "form": "10-K", "url": url})
            if len(out) >= max_items:
                break
    return out

def fetch_news_snippets(query: str, max_items: int = 5) -> List[Dict[str, Any]]:
    try:
        import feedparser
    except Exception:
        return []
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(url)
    out: List[Dict[str, Any]] = []
    for e in feed.entries[:max_items]:
        out.append({
            "date": getattr(e, "published", "")[:16],
            "title": getattr(e, "title", ""),
            "source": getattr(getattr(e, "source", {}), "title", ""),
            "link": getattr(e, "link", ""),
        })
    return out

def summarize_10k_business_priorities(url: str) -> Optional[str]:
    """
    Fetch the 10-K primary document and summarize ONLY near-term business priorities.
    Requires beautifulsoup4 installed.
    """
    html = _req_text(url)
    if not html:
        return None
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return "Install beautifulsoup4 to enable 10-K summarization."
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    # Keep it small for LLM context
    text = re.sub(r"\n{2,}", "\n", text)
    text = text[:120000]  # cap to ~120k chars

    # Summarize via Ollama-first, OpenAI last
    prompt = (
        "From the following 10-K text, extract ONLY the company's primary business priorities for the next 12-24 months. "
        "Focus on growth drivers, product/market priorities, operating initiatives, capital allocation, and risks explicitly tied to priorities. "
        "Output concise bullet points.\n\n=== 10-K TEXT START ===\n"
        + text +
        "\n=== 10-K TEXT END ==="
    )
    try:
        import ollama
        model = os.getenv("OLLAMA_MODEL", "llama3:8b")
        r = ollama.chat(model=model, messages=[{"role":"user","content": prompt}], options={"temperature":0.2})
        return r["message"]["content"].strip()
    except Exception:
        pass
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model = os.getenv("OPENAI_MODEL","gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"user","content": prompt}],
            temperature=0.2
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None
