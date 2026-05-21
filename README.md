# CS Application Agent

An AI agent that researches CS graduate programs on your behalf. Give it a school and program name and it will fetch deadlines, language requirements, tuition, funding details, and real application essays — all from live web sources — and save a structured Markdown file under `schools/` for every program you ask about.

## What it looks like

While a search is in progress, two lines float at the bottom of your terminal — the current website being read above a live progress bar that fills as required fields are found. Permanent output (your prompt, the agent's reply, save confirmations) appears above the block as it scrolls past.

```
You: Tell me about Stanford CS PhD

  📄 Saved → schools/Stanford University/PhD Computer Science.md

Agent:
## Stanford University — PhD Computer Science

### Deadline
December 5

### Language Requirements
- TOEFL minimum: 100
- IELTS minimum: 7.0
- Other accepted tests: None listed
- English-institution waiver: Not specified
- Notes: TOEFL preferred; PTE Academic also accepted

### Tuition & Funding
- Tuition (local/domestic):       US$58,416/year
- Tuition (international/non-local): US$58,416/year
- Funding: All admitted PhD students receive full tuition coverage, a
  monthly stipend (~$48k/year), and health insurance for five years
  via RA, TA, or fellowship assignments.

### Program Length
5 years

### Courses
Not listed on official page

### Application Examples & Admission Stats
Acceptance rate ~5%. Admitted students typically have GPA 3.9+,
significant research experience, and strong publication records.
SOP tip: name 2–3 faculty whose research aligns with yours and
articulate why Stanford specifically.

 ▸  Reading:   https://cs.stanford.edu/admissions/phd-admissions
 ●  Progress  [███████] 7/7  all fields found
You:
```

## Architecture

```
User prompt
  └── LLM orchestrator (any supported provider — see below)
        │  one tool call per response, sequential per program
        ├── search_program(school, program, region?)
        │     web.search() → URL quality ranking → best .edu/.ac.* page
        ├── collect_program_info(url, school, program)
        │     web.extract() → LLM extraction → sparse-result retry → JSON cache
        │     → file saved immediately to schools/{School}/{Program}.md
        └── fetch_application_examples(school, program)
              web.search() → web.extract() per page → LLM summarisation → JSON cache
              → re-saves the program file with SOP/stats sections appended

  After every turn ──► checker.py validates the ProgramInfo struct
                        Missing fields? → auto follow-up turn (once)
```

**Key design decisions**

- **One program at a time.** `parallel_tool_calls=False` (OpenAI) /
  `disable_parallel_tool_use=True` (Anthropic) plus a strict
  system-prompt rule force the model to complete `search → collect → examples → answer` for one program before issuing any tool call for the next. No interleaved work.
- **Real-time save.** The Markdown file is written the moment `collect_program_info` returns. If the model later finds additional fields (or examples), the file is rewritten with the merged union. Ctrl-C halfway through still leaves a usable partial file on disk.
- **Floating status panel.** A persistent two-line block at the visible bottom of the terminal — current URL on top, field-completeness progress bar (e.g. `[████░░░] 4/7 missing: IELTS · waiver · length`) on the bottom — updates in place during work and never accumulates in scrollback.
- **Provider-agnostic LLM layer** (`llm.py`). Swap any supported provider with one env var. The same abstraction drives both the agent's tool-calling loop and the internal extraction calls. DeepSeek reasoning/thinking models are handled transparently (`reasoning_content` is preserved across turns).
- **Provider-agnostic web layer** (`tools/web.py`). Tavily first; DuckDuckGo (no key) and `requests + BeautifulSoup` are automatic fallbacks. Fallback warnings fire once per session.
- **Deterministic completeness checker** (`checker.py`). After every turn, seven required fields are validated against the raw `ProgramInfo` struct. Missing fields trigger one automatic follow-up search, independent of the LLM's phrasing.
- **Fixed response format.** The system prompt enforces seven named sections in every program answer so responses are structurally consistent.
- **Auto-retry on sparse pages.** If `collect_program_info` lands on a shallow page (e.g. an FAQ), it searches the same domain for a richer requirements page and merges both extractions.
- **Safety cap.** `_MAX_TOOL_ITERATIONS = 12` per user turn. If the model keeps calling tools past that, the agent forces a no-tools final answer with whatever data was collected. Prevents runaway loops.
- **TTL'd JSON cache** (`cache/`). 7-day expiry on cached entries so deadlines from last application cycle aren't reused.

## File Layout

```
agent.py          REPL — drives the tool-calling loop, real-time save, completeness check
status.py         Persistent two-line status panel (floating at visible bottom)
checker.py        Deterministic completeness validator for ProgramInfo
llm.py            Provider-agnostic LLM abstraction (presets + custom endpoints)
models.py         Pydantic models: SearchResult, ProgramInfo, ApplicationExample
config.py         Env var loading; TAVILY_API_KEY only
clean.py          Shared cache/schools clearing logic + CLI entry point
tools/
  web.py          Unified search + extract interface with automatic fallback
  search.py       search_program — URL quality ranking (international .edu/.ac.*)
  collect.py      collect_program_info — extraction with sparse-result retry
  examples.py     fetch_application_examples — SOPs + admission stats
  export.py       save_program_md — writes schools/{School}/{Program}.md
  cache.py        7-day TTL'd JSON cache keyed by SHA-256
schools/          Generated program files (gitignored)
cache/            Generated cache (gitignored)
.env              Your provider key + Tavily key (gitignored)
```

## Setup

**1. Clone and create the conda environment**

```bash
git clone https://github.com/canary-current/CS_APP_Agent.git
cd CS_APP_Agent
conda create -n cs_app_agent python=3.11 -y
conda activate cs_app_agent
pip install -r requirements.txt
```

**2. Configure API keys**

```bash
cp .env.example .env
```

Edit `.env` — `LLM_PROVIDER` is required (no default):

```ini
LLM_PROVIDER=deepseek          # see provider table below
DEEPSEEK_API_KEY=sk-...        # key for whichever provider you chose
TAVILY_API_KEY=tvly-...        # optional — DuckDuckGo used as fallback
```

**3. Run**

```bash
python agent.py
```

If `.env` is missing or incomplete, the agent prints a configuration error with the exact env vars to set and exits cleanly — no half-running state.

## REPL Commands

| Command | What it does |
|---|---|
| `<any text>` | Ask about a program. Files are saved to `schools/{School}/{Program}.md`. |
| `/clear` | Wipe `cache/` and `schools/` (with confirmation in the bar). |
| `/clear cache` | Wipe `cache/` only — forces fresh web fetches next turn. |
| `/clear schools` | Wipe `schools/` only — re-runs generate fresh files. |
| `exit` / `quit` / `bye` | Quit cleanly. |
| `Ctrl-C` / `Ctrl-D` | Quit at the prompt. |

You can also run `python clean.py [--cache] [--schools]` from a separate shell.

## Supported LLM Providers

Set `LLM_PROVIDER` to any preset name and provide the matching API key:

| `LLM_PROVIDER` | Default model | Key env var | Where to get the key |
|---|---|---|---|
| `deepseek` | `deepseek-chat` | `DEEPSEEK_API_KEY` | platform.deepseek.com |
| `openai` | `gpt-4o-mini` | `OPENAI_API_KEY` | platform.openai.com |
| `anthropic` | `claude-haiku-4-5-20251001` | `ANTHROPIC_API_KEY` | console.anthropic.com |
| `gemini` | `gemini-2.0-flash` | `GEMINI_API_KEY` | aistudio.google.com |
| `groq` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` | console.groq.com |
| `mistral` | `mistral-small-latest` | `MISTRAL_API_KEY` | console.mistral.ai |
| `xai` | `grok-3-mini` | `XAI_API_KEY` | console.x.ai |
| `together` | `meta-llama/Llama-3-70b-chat-hf` | `TOGETHER_API_KEY` | api.together.xyz |
| `ollama` | `llama3.2` | *(none — local)* | ollama.com |

**Optional overrides** — apply to any preset:
```ini
LLM_API_KEY=    # override the preset's key var
LLM_BASE_URL=   # custom OpenAI-compatible endpoint
LLM_MODEL=      # override the preset's default model
```

For a **custom OpenAI-compatible endpoint** (LM Studio, vLLM, etc.), skip the preset and set the URL directly:

```ini
LLM_PROVIDER=local
LLM_BASE_URL=http://localhost:1234/v1
LLM_API_KEY=not-needed
LLM_MODEL=my-local-model
```

## Web Search Fallback

All web calls go through `tools/web.py`, which tries providers in order:

| Operation | Primary | Fallback |
|---|---|---|
| Search | Tavily (advanced, includes content) | DuckDuckGo via `ddgs` (no key needed) |
| Page extraction | Tavily extract (handles JS pages) | `requests` + BeautifulSoup |

The fallback activates automatically on any failure — missing key, quota exceeded, rate limit, or network error. A one-line warning appears once per session and then the agent continues silently.

## Completeness Checker

After every user turn, `checker.py` inspects the raw `ProgramInfo` struct returned by `collect_program_info` and verifies all seven required fields:

| Field | Checked condition | Critical? |
|---|---|---|
| Application deadline | not `None` | ✅ triggers sparse-retry |
| TOEFL minimum score | not `None` | ✅ |
| IELTS minimum score | not `None` | ✅ |
| English-institution waiver | not `None` (distinguished from explicit `False`) | |
| Tuition (local or international) | either non-`None` | |
| Funding details | non-empty | |
| Program length | not `None` | |

If any are missing, the agent fires one follow-up turn that names the absent fields and restricts the search to the official domain. This runs once per user query — no infinite loops.

`critical=True` fields additionally drive the in-tool sparse-page retry inside `collect_program_info` — if all three are absent from a fetched page, the tool searches the same domain for a better page before returning.

## Response Format

The system prompt enforces a fixed seven-section structure for every program response:

```
## [School] — [Program]
### Deadline
### Language Requirements
### Tuition & Funding
### Program Length
### Courses
### Application Examples & Admission Stats
```

Fields that genuinely cannot be found are stated as `"Not available"` rather than silently omitted.

## Output Files (`schools/`)

Each program gets a single Markdown file:

```
schools/
  Stanford University/
    PhD Computer Science.md
    MS Computer Science.md
  Hong Kong University of Science and Technology/
    MPhil Computer Science and Engineering.md
```

- **Full names preserved.** If you ask about "HKUST", the agent resolves to the full official name before saving. Slug-based deduplication prevents creating both `HKUST/` and `Hong Kong University of Science and Technology/` directories.
- **YAML frontmatter.** Each file starts with `school`, `program`, `source` (URL), and `updated` (date) fields, so the files double as LLM "skill" documents.
- **Real-time writes.** The file appears as soon as the first successful `collect_program_info` returns. Subsequent collect/examples calls in the same turn rewrite the file with the merged union of fields (no data is lost).
- **Idempotent overwrites.** Re-asking about a program updates its file with the latest data.

## Caching

Results are cached in `cache/` as JSON files keyed by SHA-256.

- **TTL: 7 days.** Older entries are deleted on read and re-fetched fresh. Prevents serving last cycle's deadlines.
- **Repeat queries are instant and free** for cached data.
- **Manual reset:** `/clear cache` from the REPL, or `python clean.py --cache`.

## Safety / Cost Controls

| Limit | Default | Where |
|---|---|---|
| Max tool calls per user turn | 12 | `_MAX_TOOL_ITERATIONS` in `agent.py` |
| Completeness follow-up retries | 1 per turn | `_completeness_followup` |
| Sparse-retry per collect call | 1 better-page attempt | `_retry_search` in `tools/collect.py` |
| Example pages fetched | 6 candidates, stop at 3 valid | `tools/examples.py` |
| Page content sent to LLM | up to 24k chars (collect) / 18k (examples) | adaptive truncation |

When the per-turn iteration cap is hit, the agent forces a final no-tools answer with whatever data it has, so you always get *something* back.

## Dependencies

| Package | Purpose |
|---|---|
| `openai` | OpenAI-compatible API client (DeepSeek, Gemini, Groq, Mistral, Ollama, …) |
| `anthropic` | Anthropic Claude SDK (used when `LLM_PROVIDER=anthropic`) |
| `tavily-python` | Primary web search and page extraction |
| `ddgs` | DuckDuckGo search fallback (no API key required) |
| `requests` + `beautifulsoup4` | Page extraction fallback |
| `pydantic` | Structured data models with validation |
| `python-dotenv` | `.env` loading |
