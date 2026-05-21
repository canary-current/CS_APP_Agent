"""
Unified web search and page-extraction interface.

Priority chain
  search()  → Tavily (advanced, with content) → DuckDuckGo (no key needed)
  extract() → Tavily extract              → requests + BeautifulSoup

Both functions return a normalised format so callers never touch provider APIs
directly. Add new providers here without touching any tool file.
"""

from __future__ import annotations
import re
import requests
from bs4 import BeautifulSoup

_search_fallback_warned = False
_extract_fallback_warned = False


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(
    query: str,
    max_results: int = 10,
    include_domains: list[str] | None = None,
) -> list[dict]:
    """
    Search the web and return a list of {"url", "title", "content"} dicts.
    Tries Tavily first; falls back to DuckDuckGo automatically.
    """
    global _search_fallback_warned
    try:
        return _tavily_search(query, max_results, include_domains)
    except Exception as exc:
        if not _search_fallback_warned:
            print(f"  [web] Tavily search unavailable ({exc.__class__.__name__}), using DuckDuckGo")
            _search_fallback_warned = True
        return _ddg_search(query, max_results, include_domains)


def _tavily_search(
    query: str,
    max_results: int,
    include_domains: list[str] | None,
) -> list[dict]:
    from tavily import TavilyClient
    from config import TAVILY_API_KEY
    if not TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY not set")
    client = TavilyClient(api_key=TAVILY_API_KEY)
    kwargs: dict = {
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
    }
    if include_domains:
        kwargs["include_domains"] = include_domains
    resp = client.search(query, **kwargs)
    return [
        {
            "url":     r["url"],
            "title":   r.get("title", ""),
            "content": r.get("content", ""),
        }
        for r in resp.get("results", [])
    ]


def _ddg_search(
    query: str,
    max_results: int,
    include_domains: list[str] | None,
) -> list[dict]:
    from ddgs import DDGS

    # DuckDuckGo doesn't have an include_domains param; use site: operator instead.
    if include_domains:
        site_filter = " OR ".join(f"site:{d}" for d in include_domains)
        query = f"{query} ({site_filter})"

    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "url":     r.get("href", ""),
                "title":   r.get("title", ""),
                "content": r.get("body", ""),
            })
    return results


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract(url: str) -> str | None:
    """
    Return the cleaned text content of a page, or None on failure.
    Tries Tavily extract first; falls back to requests + BeautifulSoup.
    """
    global _extract_fallback_warned
    try:
        return _tavily_extract(url)
    except Exception as exc:
        if not _extract_fallback_warned:
            print(f"  [web] Tavily extract unavailable ({exc.__class__.__name__}), fetching directly")
            _extract_fallback_warned = True
        return _bs_extract(url)


def _tavily_extract(url: str) -> str:
    from tavily import TavilyClient
    from config import TAVILY_API_KEY
    if not TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY not set")
    client = TavilyClient(api_key=TAVILY_API_KEY)
    resp = client.extract(urls=[url])
    results = resp.get("results", [])
    if not results or not results[0].get("raw_content"):
        raise ValueError("empty Tavily extract response")
    return results[0]["raw_content"]


def _bs_extract(url: str) -> str | None:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CS-App-Agent/1.0; +research)"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
    except Exception:
        return None

    # Trust chardet over the (often wrong) HTTP header for CJK and other non-ASCII pages.
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text or None
