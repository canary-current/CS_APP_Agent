"""
fetch_application_examples: find real SOPs, personal statements, and admission
statistics for a given school + program.

Strategy:
  - Run two targeted searches (essays vs. stats) via tools.web.search().
  - Fetch page content for the top results via tools.web.extract().
  - Summarise each page with the LLM.
  - Cache the full list keyed by school + program.

Unlike search_program, community sites (Reddit, GradCafe) are WELCOME here —
they are the primary source of real admission data and essay examples.

Web calls go through tools.web which tries Tavily first and falls back to
DuckDuckGo / requests+BeautifulSoup automatically.
"""

from __future__ import annotations
import json
import re
from models import ApplicationExample
from tools.cache import get_cached, set_cached
from tools.web import search as web_search, extract as web_extract
import llm

_TARGET_PER_TYPE  = 3   # stop once this many valid summaries are collected
_FETCH_CANDIDATES = 6   # fetch up to this many pages (more needed with DDG fallback)
_CHAR_LIMIT = 18_000   # cap for essay/stats pages; use full content below this

# Domains that host real SOPs / admission results — boosted in ranking
_PREFERRED_ESSAY_DOMAINS = [
    "reddit.com", "cs-sop.netlify.app", "applytophd.com",
    "thegradcafe.com", "yonatanbisk.com",
]
_PREFERRED_STATS_DOMAINS = [
    "thegradcafe.com", "reddit.com", "csrankings.org",
]

_SYSTEM = (
    "You are a concise summariser for graduate school application research. "
    "Return ONLY valid JSON — no markdown fences, no commentary."
)

_ESSAY_PROMPT = """\
The webpage below contains a statement of purpose (SOP), personal statement,
or related graduate school application essay.

Summarise it in a JSON object with these keys:
  type            – "SOP" or "personal_statement"
  summary         – 3-5 sentences covering: applicant background, research
                    experience highlighted, career goals stated, and any
                    distinctive qualities of the writing
  tips            – up to 3 concrete writing tips implied by this example
                    (list of strings, may be empty)

Webpage text ({note}):
{content}
"""

_STATS_PROMPT = """\
The webpage below contains graduate school admission results, statistics,
or applicant profiles.

Summarise in a JSON object with these keys:
  type            – "admission_stats"
  summary         – 3-5 sentences covering: typical accepted GPA range,
                    GRE scores (if mentioned), acceptance rate or competitiveness,
                    and any patterns across admitted applicants
  tips            – up to 3 actionable insights for applicants (list of strings,
                    may be empty)

Webpage text ({note}):
{content}
"""


def _normalize(s: str) -> str:
    """Collapse whitespace and lowercase for stable cache keys."""
    return " ".join(s.lower().split())


def _ranked_search(query: str, preferred_domains: list[str]) -> list[dict]:
    """Search and float results from preferred domains to the top."""
    results = web_search(query, max_results=_FETCH_CANDIDATES * 2)

    def _rank(r: dict) -> int:
        url = r["url"].lower()
        return 1 if any(d in url for d in preferred_domains) else 0

    return sorted(results, key=_rank, reverse=True)


def _truncate(content: str) -> tuple[str, str]:
    """Return (content_to_send, note_for_prompt)."""
    if len(content) <= _CHAR_LIMIT:
        return content, f"{len(content):,} chars"
    return content[:_CHAR_LIMIT], f"{_CHAR_LIMIT:,} of {len(content):,} chars (truncated)"


def _summarise_page(url: str, prompt_template: str) -> dict | None:
    """Fetch a page and return the LLM summary dict, or None on failure."""
    content = web_extract(url)
    if not content:
        return None
    content, note = _truncate(content)

    raw = llm.complete(_SYSTEM, prompt_template.format(content=content, note=note))
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def fetch_application_examples(
    school: str,
    program: str,
) -> list[ApplicationExample]:
    """
    Find real SOPs, personal statements, and admission statistics for a program.

    Args:
        school:  University name, e.g. "Stanford University".
        program: Program name, e.g. "PhD Computer Science".

    Returns:
        List of ApplicationExample (may be empty if nothing useful is found).
    """
    cache_key = f"examples:{_normalize(school)}:{_normalize(program)}"
    cached = get_cached(cache_key)
    if cached:
        return [ApplicationExample(**item) for item in cached["items"]]

    examples: list[ApplicationExample] = []

    # --- 1. Essay / SOP search ---
    essay_query = (
        f'"{school}" "{program}" statement of purpose SOP personal statement example'
    )
    essay_results = _ranked_search(essay_query, _PREFERRED_ESSAY_DOMAINS)

    for result in essay_results[:_FETCH_CANDIDATES]:
        if sum(1 for e in examples if e.type in ("SOP", "personal_statement")) >= _TARGET_PER_TYPE:
            break
        url = result["url"]
        print(f"  [examples] fetching essay page: {url}")
        summary_data = _summarise_page(url, _ESSAY_PROMPT)
        if not summary_data:
            continue
        doc_type = summary_data.get("type", "SOP")
        tips = summary_data.get("tips", [])
        full_summary = summary_data.get("summary", "")
        if tips:
            full_summary += "\n\nTips: " + "; ".join(tips)
        examples.append(ApplicationExample(
            school=school,
            program=program,
            type=doc_type,
            source_url=url,
            content_summary=full_summary,
        ))

    # --- 2. Admission stats search ---
    stats_query = (
        f'"{school}" "{program}" admission results GPA acceptance rate statistics'
    )
    stats_results = _ranked_search(stats_query, _PREFERRED_STATS_DOMAINS)

    stats_count = 0
    for result in stats_results[:_FETCH_CANDIDATES]:
        if stats_count >= _TARGET_PER_TYPE:
            break
        url = result["url"]
        print(f"  [examples] fetching stats page: {url}")
        summary_data = _summarise_page(url, _STATS_PROMPT)
        if not summary_data:
            continue
        tips = summary_data.get("tips", [])
        full_summary = summary_data.get("summary", "")
        if tips:
            full_summary += "\n\nTips: " + "; ".join(tips)
        examples.append(ApplicationExample(
            school=school,
            program=program,
            type="admission_stats",
            source_url=url,
            content_summary=full_summary,
        ))
        stats_count += 1

    set_cached(cache_key, {"items": [e.model_dump() for e in examples]})
    return examples


# ---------------------------------------------------------------------------
# Claude tool schema
# ---------------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "fetch_application_examples",
    "description": (
        "Find real statements of purpose (SOPs), personal statements, and admission "
        "statistics for a graduate CS program. Returns summaries with actionable tips."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "school": {
                "type": "string",
                "description": "University name, e.g. 'Stanford University'.",
            },
            "program": {
                "type": "string",
                "description": "Program name, e.g. 'PhD Computer Science'.",
            },
        },
        "required": ["school", "program"],
    },
}
