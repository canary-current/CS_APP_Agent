# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An AI agent that researches CS graduate programs on demand. The user names a school and program; the agent fetches deadlines, language requirements, tuition, funding, course lists, and real SOP/admission-stats examples from live web sources, then saves everything to a structured Markdown file.

## Running the Agent

```bash
conda activate cs_app_agent
python agent.py
```

The startup banner shows the active LLM provider. Type `exit` or Ctrl-C to quit.

## Architecture

Three stateless tool functions, orchestrated by an LLM in a tool-calling loop:

```
agent.py (_run_turn)
  └── llm.chat_with_tools(messages, tools)
        ├── search_program(school, program, region?)   → SearchResult (url, title, description)
        ├── collect_program_info(url, school, program) → ProgramInfo  (deadline, lang reqs, tuition, …)
        └── fetch_application_examples(school, program)→ [ApplicationExample]
```

After every user turn:
1. `checker.py` inspects the raw `ProgramInfo` struct for missing required fields.
2. If any are absent, one automatic follow-up turn fires (no infinite loops).
3. `tools/export.py` writes `schools/{Full School Name}/{Program Name}.md`.

## LLM Configuration

`llm.py` is the single abstraction for all LLM calls — both the agent's tool-calling loop and the internal extraction calls in `collect.py` / `examples.py`.

Set in `.env`:
```ini
LLM_PROVIDER=deepseek   # preset name (default)
DEEPSEEK_API_KEY=sk-…   # key matching the preset
```

Supported presets: `deepseek`, `openai`, `anthropic`, `gemini`, `groq`, `mistral`, `xai`, `together`, `ollama`.

Optional overrides (any preset):
- `LLM_API_KEY` — replaces the preset's key env var
- `LLM_BASE_URL` — custom OpenAI-compatible endpoint (LM Studio, vLLM, etc.)
- `LLM_MODEL` — replaces the preset's default model

`config.py` only exposes `TAVILY_API_KEY`. All provider key resolution lives in `llm.py`.

## Message Format

`agent.py` always stores conversation history in **OpenAI format** (including `tool_calls` / `tool` role messages). `llm._to_anthropic_messages()` converts this to Anthropic format on each call when `LLM_PROVIDER=anthropic`. Never pass Anthropic-format messages directly to `chat_with_tools`.

## Web Layer

All network calls go through `tools/web.py`:
- `web.search(query, ...)` — Tavily first, falls back to DuckDuckGo (`ddgs`)
- `web.extract(url)` — Tavily extract first, falls back to `requests` + BeautifulSoup

`TAVILY_API_KEY` is optional; the fallback activates automatically on any failure.

## Data Models (`models.py`)

```python
ProgramInfo:
  school, program, url, deadline
  language_requirements: LanguageRequirements
    toefl_min, ielts_min, english_institution_waiver (bool | None), other_tests, notes
  tuition: Tuition
    local, international, notes
  funding, length_years, courses

ApplicationExample:
  school, program, type ("SOP" | "personal_statement" | "admission_stats")
  source_url, content_summary
```

`english_institution_waiver` is `bool | None` — `None` means "not found", never conflate with `False`.

## Completeness Checker (`checker.py`)

`REQUIRED` is a list of `FieldSpec(label, is_missing)`. Add new required fields here. `missing_fields(info)` returns labels of absent fields; `follow_up_prompt(info, missing)` generates the auto follow-up instruction.

Current required fields: deadline, TOEFL min, IELTS min, English waiver, tuition (local or international), funding, program length.

## Markdown Export (`tools/export.py`)

Output: `schools/{Full School Name}/{Program Name}.md` with YAML frontmatter.

- `_safe(text)` strips filesystem-illegal chars but preserves spaces and original case.
- `_resolve_school_dir(school)` does slug-based dedup so "HKUST" and "Hong Kong University of Science and Technology" resolve to the same folder. Always pass the full official name from the system prompt to avoid creating duplicate folders.
- `save_program_md` raises `ValueError` if `info.url` is empty.

## Cache

SHA-256 keyed JSON files in `cache/`. Delete the folder to force a live re-fetch.

## Environment

- Python 3.11, conda env `cs_app_agent` at `/opt/miniconda3/envs/cs_app_agent/`
- Dependencies: `openai`, `anthropic`, `tavily-python`, `ddgs`, `requests`, `beautifulsoup4`, `pydantic`, `python-dotenv`
- Never commit `.env` — it is in `.gitignore`
