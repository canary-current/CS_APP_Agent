# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI agent that helps undergraduate students research and apply to CS graduate programs. It has three core capabilities:

1. **Program search** — given a school name, program name, and optional region, find the program's official page.
2. **Program data collection** — scrape/fetch structured information: application deadlines, language test requirements (TOEFL/IELTS minimums and English-institution waivers), funding details, program length, and course lists.
3. **Application intelligence** — retrieve successful application examples, sample SOPs, personal statements, and admission statistics for each target school.

## Intended Architecture

The agent is designed as a pipeline of tools orchestrated by an LLM (Claude API). Each capability maps to a distinct tool that the agent can invoke:

```
User Query
    └── Agent (LLM orchestrator)
            ├── search_program(school, program, region?) → URL + basic metadata
            ├── collect_program_info(url) → structured ProgramInfo dict
            └── fetch_application_examples(school, program) → list of essays/stats
```

**Key design decisions:**
- Tools are stateless functions; the LLM holds conversation context.
- Program data is cached locally (e.g., JSON or SQLite) so repeat lookups don't re-fetch.
- Web search is done via a search API (e.g., Brave Search, SerpAPI, or Tavily); page scraping is done with `requests` + `BeautifulSoup` or `playwright` for JS-heavy pages.
- The agent loop lives in `agent.py`; individual tools live under `tools/`.

## Expected File Layout (to be created)

```
agent.py            # Main entry point — runs the agent REPL/CLI
tools/
  search.py         # search_program tool
  collect.py        # collect_program_info tool
  examples.py       # fetch_application_examples tool
  cache.py          # local caching helpers
models.py           # Pydantic models for ProgramInfo, ApplicationExample, etc.
config.py           # API keys and settings loaded from .env
requirements.txt
.env.example        # Template for required env vars (never commit .env)
```

## Environment & Setup

Use a virtual environment:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Required environment variables (copy `.env.example` → `.env`):
- `ANTHROPIC_API_KEY` — Claude API key for the agent orchestrator
- `SEARCH_API_KEY` — key for whichever search API is used (Tavily, Brave, SerpAPI)

Run the agent:
```bash
python agent.py
```

## Language & Dependencies

- Python 3.11+
- `anthropic` SDK for the LLM orchestrator
- `requests` / `httpx` for HTTP; `beautifulsoup4` for HTML parsing
- `pydantic` for structured data models
- `python-dotenv` for env var loading
- `playwright` (optional) for JavaScript-rendered pages

## Data Model

`ProgramInfo` should capture at minimum:
- `school`, `program`, `url`
- `deadline` (date or string)
- `language_requirements`: dict with `toefl_min`, `ielts_min`, `english_institution_waiver` (bool)
- `funding`: free-text or structured (RA/TA availability, stipend amounts)
- `length_years`
- `courses`: list of course names/codes

`ApplicationExample` should capture:
- `school`, `program`, `type` (SOP / personal statement / admission stats)
- `source_url`, `content_summary`
