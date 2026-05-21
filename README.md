# CS Application Agent

An AI agent that researches CS graduate programs on your behalf. Give it a school and program name and it will fetch deadlines, language requirements, funding details, and real application essays — all from live web sources.

## Demo

```
You: Tell me about the PhD CS program at CMU — deadlines, language requirements, and funding.

  ⚙ search  Carnegie Mellon University — PhD Computer Science
  ⚙ collect https://admissions.scs.cmu.edu/portal/apply_gr
  ⚙ examples Carnegie Mellon University — PhD Computer Science

Agent: Here's a comprehensive summary of the PhD in Computer Science at Carnegie Mellon University.

## Deadlines
Applications for Fall 2026 open Summer 2025. Historically the deadline falls in late
October / early November of the prior year.

## Language Requirements
No waivers for non-native speakers. TOEFL ITP Plus for China is not accepted;
mainland China applicants are strongly encouraged to take the IELTS instead.

## Funding
All admitted PhD students receive a stipend, full tuition, university fees, and
health insurance — for both domestic and international students.
...
```

## Architecture

The agent is a thin orchestration loop around three stateless tools:

```
User prompt
  └── DeepSeek-V3 (orchestrator, tool-calling)
        ├── search_program(school, program, region?)
        │     Tavily search → ranked by URL quality → returns best .edu page
        ├── collect_program_info(url, school, program)
        │     Tavily extract → LLM extraction → auto-retry on sparse results → JSON cache
        └── fetch_application_examples(school, program)
              Tavily search (essays + stats) → LLM summarisation → JSON cache
```

**Key design decisions**

- **Stateless tools** — each tool is a pure function; the LLM holds all conversation state.
- **Provider-agnostic LLM layer** (`llm.py`) — swap between DeepSeek and Anthropic Claude by changing one env var.
- **Auto-retry on sparse pages** — if `collect_program_info` finds a page with no deadline or language scores, it searches the same domain for a richer requirements page and merges the results.
- **Local JSON cache** (`cache/`) — repeat lookups never re-fetch. Delete the folder to force a refresh.

## File Layout

```
agent.py          Main entry point — REPL that drives the tool-calling loop
llm.py            Provider abstraction (DeepSeek / Anthropic)
models.py         Pydantic models: SearchResult, ProgramInfo, ApplicationExample
config.py         Env var loading with early failure on missing keys
tools/
  search.py       search_program — Tavily search with URL quality ranking
  collect.py      collect_program_info — page extraction with sparse-result retry
  examples.py     fetch_application_examples — SOP + admission stats finder
  cache.py        JSON cache keyed by SHA-256 of the lookup key
requirements.txt
.env.example
```

## Setup

**1. Clone and create the conda environment**

```bash
git clone https://github.com/canary_cuurent/CS_APP_Agent.git
cd CS_APP_Agent
conda create -n cs_app_agent python=3.11 -y
conda activate cs_app_agent
pip install -r requirements.txt
```

**2. Configure API keys**

```bash
cp .env.example .env
```

Edit `.env`:

```ini
DEEPSEEK_API_KEY=sk-...        # required — get one at platform.deepseek.com
TAVILY_API_KEY=tvly-...        # required — free tier at tavily.com (1 000 credits/month)
ANTHROPIC_API_KEY=sk-ant-...   # optional — only needed if LLM_PROVIDER=anthropic
LLM_PROVIDER=deepseek          # "deepseek" (default) or "anthropic"
```

**3. Run**

```bash
python agent.py
```

## API Keys

| Key | Where to get it | Free tier |
|---|---|---|
| `DEEPSEEK_API_KEY` | [platform.deepseek.com](https://platform.deepseek.com) | $5 credit on sign-up |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com) | 1 000 credits / month |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Optional |

## Switching LLM Provider

Set `LLM_PROVIDER` in `.env`:

```ini
LLM_PROVIDER=anthropic   # uses claude-haiku-4-5 for tool extraction
LLM_PROVIDER=deepseek    # uses deepseek-chat (DeepSeek-V3) — default
```

The orchestrator (agent loop) always uses DeepSeek regardless of `LLM_PROVIDER` — only the internal extraction calls inside `collect_program_info` and `fetch_application_examples` respect this setting.

## Caching

Fetched pages and LLM extractions are cached in `cache/` as JSON files keyed by a SHA-256 hash of the URL or lookup key. This means:

- Repeat queries for the same program are instant and free.
- To force a re-fetch (e.g., after a deadline update), delete `cache/` or the specific file.

## Dependencies

| Package | Purpose |
|---|---|
| `openai` | DeepSeek API (OpenAI-compatible) + agent tool-calling loop |
| `anthropic` | Optional Claude backend |
| `tavily-python` | Web search and page extraction |
| `pydantic` | Structured data models with validation |
| `python-dotenv` | `.env` loading |
| `beautifulsoup4` | HTML parsing (available for custom scraping extensions) |
