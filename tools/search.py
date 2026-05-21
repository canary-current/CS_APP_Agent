"""
search_program: find a graduate CS program's official admissions page.

Uses Tavily search to locate the most authoritative URL for the given
school + program combination, then returns basic metadata (title,
description, URL) ready for the collect tool to scrape.
"""

from __future__ import annotations
import re
from tavily import TavilyClient
from config import TAVILY_API_KEY
from models import SearchResult

_client = TavilyClient(api_key=TAVILY_API_KEY)

# Domains that are almost certainly NOT the official program page.
_NOISE_DOMAINS = {
    "reddit.com", "quora.com", "youtube.com", "linkedin.com",
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "wikipedia.org", "niche.com", "collegeboard.org", "usnews.com",
    "prepscholar.com", "magoosh.com", "gradcafe.com",
}

# Path segments that indicate a rich requirements/admissions page (higher = better)
_GOOD_SEGMENTS = ["requirements", "admissions", "apply", "application", "prospective"]
# Path segments that indicate a shallow or off-topic page (penalised)
_BAD_SEGMENTS  = ["faq", "frequently-asked", "contact", "people", "faculty", "news", "event"]


def _score_url(url: str) -> int:
    path = url.lower().split("?")[0]
    score = 0
    for seg in _GOOD_SEGMENTS:
        if seg in path:
            score += 2
    for seg in _BAD_SEGMENTS:
        if seg in path:
            score -= 3
    return score


def _is_official(url: str) -> bool:
    url_lower = url.lower()
    if any(noise in url_lower for noise in _NOISE_DOMAINS):
        return False
    return ".edu" in url_lower or ".ac." in url_lower or ".university" in url_lower


def _build_query(school: str, program: str, region: str | None) -> str:
    parts = [school, program, "graduate admissions"]
    if region:
        parts.append(region)
    return " ".join(parts)


def search_program(
    school: str,
    program: str,
    region: str | None = None,
) -> SearchResult:
    """
    Find the official admissions page for a CS graduate program.

    Args:
        school:  University name, e.g. "Stanford University".
        program: Program name, e.g. "MS Computer Science" or "PhD Computer Science".
        region:  Optional geographic filter, e.g. "California" or "USA".

    Returns:
        SearchResult with the best-matching URL and page metadata.

    Raises:
        ValueError: if no suitable result is found.
    """
    query = _build_query(school, program, region)

    response = _client.search(
        query=query,
        search_depth="advanced",
        max_results=10,
        include_answer=False,
    )

    results = response.get("results", [])

    # Rank: official domain first, then by URL quality score.
    official = [r for r in results if _is_official(r["url"])]
    ranked = sorted(official, key=lambda r: _score_url(r["url"]), reverse=True)
    best = ranked[0] if ranked else (results[0] if results else None)

    if best is None:
        raise ValueError(
            f"No results found for '{program}' at '{school}'"
            + (f" in {region}" if region else "")
        )

    return SearchResult(
        school=school,
        program=program,
        url=best["url"],
        title=best.get("title", ""),
        description=best.get("content", "")[:500],
    )


# ---------------------------------------------------------------------------
# Claude tool schema (used by agent.py when registering tools)
# ---------------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "search_program",
    "description": (
        "Search for a CS graduate program's official admissions page. "
        "Returns the URL, page title, and a short description. "
        "Call this first before collecting detailed program information."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "school": {
                "type": "string",
                "description": "Full university name, e.g. 'Stanford University'.",
            },
            "program": {
                "type": "string",
                "description": "Graduate program name, e.g. 'PhD Computer Science'.",
            },
            "region": {
                "type": "string",
                "description": "Optional geographic filter, e.g. 'California' or 'Europe'.",
            },
        },
        "required": ["school", "program"],
    },
}
