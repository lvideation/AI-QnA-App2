# app/external/company.py
import os, re, time, json
from typing import Dict, Any, List, Optional
from urllib.parse import quote_plus

USER_AGENT = os.getenv("SEC_EMAIL") or "AI-QnA-App2 (contact: set SEC_EMAIL in .env)"

def _req_json(url: str) -> Optional[dict]:
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        if r.status_code == 200:
            return r.json()
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
    # Try direct ticker match
    for _, row in data.items():
        if row.get("ticker","").lower() == ql:
            return f'{int(row["cik_str"]):010d}'
    # Try name contains
    best = None
    for _, row in data.items():
        name = row.get("title","").lower()
        if ql in name:
            best = row
            break
    if best:
        return f'{int(best["cik_str"]):010d}'
    return None

def fetch_sec_10k_items(company_or_ticker: str, max_items: int = 5) -> List[Dict[str, Any]]:
    """
    Returns recent 10-K metadata via SEC submissions API (no API key).
    Set SEC_EMAIL in .env to be a good citizen (used in User-Agent).
    """
    cik = _match_cik_for_query(company_or_ticker)
    if not cik:
        return []
    sub = _req_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    if not sub: return []
    forms = sub.get("filings", {}).get("recent", {})
    keys = list(forms.keys())
    # Build rows where form == 10-K
    out = []
    for i, form in enumerate(forms.get("form", [])):
        if str(form).lower() == "10-k":
            date = forms.get("filingDate", [""])[i]
            accn = forms.get("accessionNumber", [""])[i]
            primary = forms.get("primaryDocument", [""])[i]
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-','')}/{primary}"
            out.append({
                "filing_date": date,
                "form": "10-K",
                "accession": accn,
                "doc": primary,
                "url": url
            })
            if len(out) >= max_items:
                break
    return out

def fetch_news_snippets(query: str, max_items: int = 8) -> List[Dict[str, Any]]:
    """
    Uses Google News RSS (no key) via feedparser.
    """
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
