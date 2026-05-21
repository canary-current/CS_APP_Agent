"""
collect_program_info: scrape a program page and return structured ProgramInfo.

Flow:
  1. Check local JSON cache (keyed by URL).
  2. Fetch page text via tools.web.extract(); run LLM extraction.
  3. If critical fields are missing (sparse result), search the same domain for
     a more targeted requirements/admissions page and merge the two extractions.
  4. Cache and return.

Web calls go through tools.web which tries Tavily first and falls back to
DuckDuckGo / requests+BeautifulSoup automatically.
"""

from __future__ import annotations
import json
import re
from urllib.parse import urlparse
from models import ProgramInfo, LanguageRequirements, Tuition
from tools.cache import get_cached, set_cached
from tools.web import search as web_search, extract as web_extract
from checker import CRITICAL_RAW_FIELDS
import llm

_SYSTEM = (
    "You are a precise information extractor. "
    "Return ONLY valid JSON — no markdown fences, no commentary."
)

_PROMPT = """\
Extract graduate program details from the webpage text below.

Return a JSON object with these keys (use null when information is absent):
  deadline              – application deadline as a readable string, e.g. "December 15, 2025"
  toefl_min             – minimum TOEFL iBT total score as an integer
  ielts_min             – minimum IELTS overall band score as a float
  english_waiver        – true if graduates of English-taught institutions are exempt from
                          language tests; false if explicitly no waiver; null if not mentioned
  other_language_tests  – list of other accepted tests with their minimums, e.g.
                          ["Duolingo English Test: 120+", "PTE Academic: 65+"];
                          empty list if none mentioned
  language_notes        – any extra language-test details worth keeping (string or "")
  tuition_local         – annual tuition for local/domestic students as a string with currency,
                          e.g. "HK$42,100/year" or "US$18,000/year"; null if not found
  tuition_international – annual tuition for international/non-local students as a string with
                          currency, e.g. "HK$42,100/year"; null if not found or same as local
  tuition_notes         – any clarifying notes on tuition (per credit, fee waivers, etc.) or ""
  funding               – concise summary of RA/TA/fellowship/stipend availability (string or "")
  length_years          – program length in years as a number (e.g. 2, 4, 5.5)
  courses               – list of course names or codes explicitly mentioned (may be empty)

Webpage text ({note}):
{content}
"""

# Send the full page for short content; cap long pages at this limit.
# Most admission pages are under 20 k chars; pushing past that adds noise.
_CHAR_LIMIT = 24_000


def _is_sparse(data: dict) -> bool:
    return all(data.get(f) is None for f in CRITICAL_RAW_FIELDS)


def _truncate(content: str) -> tuple[str, str]:
    """Return (content_to_send, note_for_prompt)."""
    if len(content) <= _CHAR_LIMIT:
        return content, f"{len(content):,} chars"
    return content[:_CHAR_LIMIT], f"{_CHAR_LIMIT:,} of {len(content):,} chars (truncated)"


def _extract_from_url(url: str) -> dict | None:
    """Fetch a URL and run LLM extraction. Returns raw dict or None on failure."""
    content = web_extract(url)
    if not content:
        return None
    content, note = _truncate(content)

    raw = llm.complete(_SYSTEM, _PROMPT.format(content=content, note=note))
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _retry_search(school: str, program: str, base_url: str) -> dict | None:
    """
    Search the original domain for a richer requirements/admissions page and
    extract it. Returns a raw data dict, or None if nothing better was found.
    """
    domain = urlparse(base_url).netloc
    query = f"{school} {program} admissions requirements TOEFL deadline"
    try:
        results = web_search(query, max_results=5, include_domains=[domain])
    except Exception:
        return None

    for result in results:
        candidate_url = result["url"]
        if candidate_url == base_url:
            continue
        data = _extract_from_url(candidate_url)
        if data and not _is_sparse(data):
            return data
    return None


def _merge(base: dict, extra: dict) -> dict:
    """Fill None/missing values in base with values from extra."""
    merged = dict(base)
    for key, val in extra.items():
        if merged.get(key) is None and val is not None:
            merged[key] = val
    merged["courses"] = list({
        c for c in (base.get("courses") or []) + (extra.get("courses") or [])
    })
    return merged


def collect_program_info(url: str, school: str, program: str) -> ProgramInfo:
    """
    Scrape a program admissions page and return structured ProgramInfo.

    If the initial page is sparse (missing deadline + language requirements),
    automatically searches the same domain for a better page and merges results.

    Args:
        url:     The program's official admissions page URL (from search_program).
        school:  University name — passed through to the returned model.
        program: Program name — passed through to the returned model.

    Returns:
        ProgramInfo with all available fields populated.

    Raises:
        ValueError: if the page cannot be fetched or parsed.
    """
    cached = get_cached(url)
    if cached:
        return ProgramInfo(**cached)

    # --- 1. Primary extraction ---
    data = _extract_from_url(url)
    if data is None:
        raise ValueError(f"Could not fetch or parse: {url}")

    # --- 2. Retry on sparse results ---
    if _is_sparse(data):
        print(f"  [collect] sparse result — searching {urlparse(url).netloc} for a better page…")
        extra = _retry_search(school, program, url)
        if extra:
            data = _merge(data, extra)

    # --- 3. Build model ---
    info = ProgramInfo(
        school=school,
        program=program,
        url=url,
        deadline=data.get("deadline"),
        language_requirements=LanguageRequirements(
            toefl_min=data.get("toefl_min"),
            ielts_min=data.get("ielts_min"),
            english_institution_waiver=(
                None if data.get("english_waiver") is None
                else bool(data["english_waiver"])
            ),
            other_tests=data.get("other_language_tests") or [],
            notes=data.get("language_notes", ""),
        ),
        tuition=Tuition(
            local=data.get("tuition_local"),
            international=data.get("tuition_international"),
            notes=data.get("tuition_notes", ""),
        ),
        funding=data.get("funding", ""),
        length_years=data.get("length_years"),
        courses=data.get("courses", []),
    )

    set_cached(url, info.model_dump())
    return info


# ---------------------------------------------------------------------------
# Claude tool schema
# ---------------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "collect_program_info",
    "description": (
        "Fetch and extract structured information from a graduate program's admissions page: "
        "deadlines, language test requirements, funding, program length, and course list. "
        "Call search_program first to get the URL."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Admissions page URL returned by search_program.",
            },
            "school": {
                "type": "string",
                "description": "University name, e.g. 'Stanford University'.",
            },
            "program": {
                "type": "string",
                "description": "Program name, e.g. 'PhD Computer Science'.",
            },
        },
        "required": ["url", "school", "program"],
    },
}
