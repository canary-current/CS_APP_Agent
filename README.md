# CS Application Agent

An AI agent that researches CS graduate programs on your behalf. Give it a school and program name and it will fetch deadlines, language requirements, funding details, and real application essays — all from live web sources.

## Demo

```
You: Tell me about the funded MS CS program at UIUC.

  ⚙ search  University of Illinois Urbana-Champaign — MS Computer Science
  ⚙ collect https://cs.illinois.edu/admissions/graduate/applications
  ⚙ examples University of Illinois Urbana-Champaign — MS Computer Science

  ⚠ Completeness check: 3 required field(s) missing — auto-searching…
  ⚙ collect https://cs.illinois.edu/admissions/graduate/requirements

Agent (after completeness check):

## University of Illinois Urbana-Champaign — MS Computer Science

### Deadline
December 15

### Language Requirements
- TOEFL minimum: 102
- IELTS minimum: 7.0
- English-institution waiver: Yes — applicants from accredited English-taught
  institutions may be exempt. Contact the department to confirm eligibility.
- Notes: Speaking sub-score of 24+ required for TA eligibility.

### Funding
MS with Thesis students are eligible for Research Assistantships (RA) and
Teaching Assistantships (TA), which typically cover full tuition and provide
a monthly stipend (~$2,000–$2,500). Fellowships are available but competitive.
The Professional MCS track is self-funded.

### Program Length
1.5–2 years (thesis track)

### Courses
Not listed on official page

### Application Examples & Admission Stats
Acceptance rate ~22%. Admitted students typically have strong academic records.
SOP tip: name specific faculty whose research aligns with yours.
```

## Architecture

```
User prompt
  └── LLM orchestrator (any supported provider — see below)
        ├── search_program(school, program, region?)
        │     web.search() → URL quality ranking → best .edu/.ac. page
        ├── collect_program_info(url, school, program)
        │     web.extract() → LLM extraction → sparse-result retry → JSON cache
        └── fetch_application_examples(school, program)
              web.search() → web.extract() per page → LLM summarisation → JSON cache

  After every turn ──► checker.py validates the ProgramInfo struct
                        Missing fields? → auto follow-up turn (once)
```

**Key design decisions**

- **Stateless tools** — each tool is a pure function; the LLM holds all conversation state.
- **Provider-agnostic LLM layer** (`llm.py`) — swap any supported provider with one env var. The same abstraction drives both the agent's tool-calling loop and the internal extraction calls.
- **Provider-agnostic web layer** (`tools/web.py`) — all network calls go through a single module. Tavily is tried first; DuckDuckGo (no key) and requests+BeautifulSoup are automatic fallbacks.
- **Deterministic completeness checker** (`checker.py`) — after every turn, required fields are validated against the raw `ProgramInfo` struct. Missing fields trigger one automatic follow-up search, independent of the LLM's phrasing choices.
- **Fixed response format** — the system prompt enforces seven named sections in every program answer so responses are structurally consistent.
- **Auto-retry on sparse pages** — if `collect_program_info` lands on a shallow page, it searches the same domain for a richer requirements page and merges both extractions.
- **Local JSON cache** (`cache/`) — repeat lookups never re-fetch. Delete the folder to force a refresh.

## File Layout

```
agent.py          REPL — drives the tool-calling loop and completeness check
checker.py        Deterministic completeness validator for ProgramInfo
llm.py            Provider-agnostic LLM abstraction (presets + custom endpoints)
models.py         Pydantic models: SearchResult, ProgramInfo, ApplicationExample
config.py         Env var loading; TAVILY_API_KEY is optional
tools/
  web.py          Unified search + extract interface with automatic fallback
  search.py       search_program — URL quality ranking
  collect.py      collect_program_info — extraction with sparse-result retry
  examples.py     fetch_application_examples — SOP + admission stats
  cache.py        JSON cache keyed by SHA-256 of the lookup key
requirements.txt
.env.example
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

Edit `.env` — set `LLM_PROVIDER` and the matching key:

```ini
LLM_PROVIDER=deepseek          # see provider table below
DEEPSEEK_API_KEY=sk-...        # key for whichever provider you chose
TAVILY_API_KEY=tvly-...        # optional — DuckDuckGo used as fallback
```

**3. Run**

```bash
python agent.py
```

## Supported LLM Providers

Set `LLM_PROVIDER` to any preset name and provide the matching API key:

| `LLM_PROVIDER` | Default model | Key env var | Where to get the key |
|---|---|---|---|
| `deepseek` *(default)* | `deepseek-chat` | `DEEPSEEK_API_KEY` | platform.deepseek.com |
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

**Web search keys:**

| Key | Where to get it | Required? |
|---|---|---|
| `TAVILY_API_KEY` | tavily.com | No — DuckDuckGo used as fallback |

## Web Search Fallback

All web calls go through `tools/web.py`, which tries providers in order:

| Operation | Primary | Fallback |
|---|---|---|
| Search | Tavily (advanced, includes content) | DuckDuckGo via `ddgs` (no key needed) |
| Page extraction | Tavily extract (handles JS pages) | `requests` + BeautifulSoup |

The fallback activates automatically on any failure — missing key, quota exceeded, rate limit, or network error. The agent continues without interruption.

## Completeness Checker

After every user turn, `checker.py` inspects the raw `ProgramInfo` struct returned by `collect_program_info` and verifies that all six required fields are present:

| Field | Checked condition |
|---|---|
| Application deadline | not `None` |
| TOEFL minimum score | not `None` |
| IELTS minimum score | not `None` |
| English-institution waiver | not `None` (distinguished from explicit `False`) |
| Funding details | non-empty |
| Program length | not `None` |

If any are missing, the agent automatically fires one follow-up turn that names the exact absent fields and restricts the search to the official domain. This runs once per user query — no infinite loops.

## Response Format

The system prompt enforces a fixed seven-section structure for every program response:

```
## [School] — [Program]
### Deadline
### Language Requirements
### Funding
### Program Length
### Courses
### Application Examples & Admission Stats
```

Fields that genuinely cannot be found are stated as "Not available" rather than silently omitted.

## Switching LLM Provider

Change one line in `.env` — both the agent's tool-calling loop and the internal extraction calls switch together:

```ini
LLM_PROVIDER=deepseek    # default
LLM_PROVIDER=openai
LLM_PROVIDER=anthropic
LLM_PROVIDER=groq        # fast and free-tier friendly
LLM_PROVIDER=ollama      # fully local, no key needed
```

For a **custom OpenAI-compatible endpoint** (LM Studio, vLLM, etc.), skip the preset and set the URL directly:

```ini
LLM_BASE_URL=http://localhost:1234/v1
LLM_API_KEY=not-needed
LLM_MODEL=my-local-model
```

## Caching

Results are cached in `cache/` as JSON files keyed by a SHA-256 hash of the URL or lookup key.

- Repeat queries for the same program are instant and free.
- To force a live re-fetch (e.g. after a deadline changes), delete `cache/` or the specific file.

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
