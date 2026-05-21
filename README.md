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
  └── DeepSeek-V3 (orchestrator, tool-calling loop)
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
- **Provider-agnostic web layer** (`tools/web.py`) — all network calls go through a single module. Tavily is tried first; DuckDuckGo (no key) and requests+BeautifulSoup are automatic fallbacks.
- **Provider-agnostic LLM layer** (`llm.py`) — swap between DeepSeek and Anthropic Claude by changing one env var.
- **Deterministic completeness checker** (`checker.py`) — after every turn, required fields are validated against the raw `ProgramInfo` struct. Missing fields trigger one automatic follow-up search, independent of the LLM's phrasing choices.
- **Fixed response format** — the system prompt enforces seven named sections in every program answer so responses are structurally consistent.
- **Auto-retry on sparse pages** — if `collect_program_info` lands on a shallow page, it searches the same domain for a richer requirements page and merges both extractions.
- **Local JSON cache** (`cache/`) — repeat lookups never re-fetch. Delete the folder to force a refresh.

## File Layout

```
agent.py          REPL — drives the tool-calling loop and completeness check
checker.py        Deterministic completeness validator for ProgramInfo
llm.py            LLM abstraction (DeepSeek / Anthropic)
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

Edit `.env`:

```ini
DEEPSEEK_API_KEY=sk-...        # required — platform.deepseek.com
TAVILY_API_KEY=tvly-...        # optional — tavily.com (free tier: 1 000 credits/month)
ANTHROPIC_API_KEY=sk-ant-...   # optional — only needed if LLM_PROVIDER=anthropic
LLM_PROVIDER=deepseek          # "deepseek" (default) or "anthropic"
```

**3. Run**

```bash
python agent.py
```

## API Keys

| Key | Where to get it | Required? |
|---|---|---|
| `DEEPSEEK_API_KEY` | [platform.deepseek.com](https://platform.deepseek.com) | Yes |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com) | No — DuckDuckGo used as fallback |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | No — only if `LLM_PROVIDER=anthropic` |

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

```ini
LLM_PROVIDER=deepseek    # DeepSeek-V3 via OpenAI-compatible API (default)
LLM_PROVIDER=anthropic   # Claude Haiku via Anthropic SDK
```

The agent's tool-calling loop always uses DeepSeek. `LLM_PROVIDER` controls only the internal extraction calls inside `collect_program_info` and `fetch_application_examples`.

## Caching

Results are cached in `cache/` as JSON files keyed by a SHA-256 hash of the URL or lookup key.

- Repeat queries for the same program are instant and free.
- To force a live re-fetch (e.g. after a deadline changes), delete `cache/` or the specific file.

## Dependencies

| Package | Purpose |
|---|---|
| `openai` | DeepSeek API (OpenAI-compatible) + agent tool-calling loop |
| `anthropic` | Optional Claude backend |
| `tavily-python` | Primary web search and page extraction |
| `ddgs` | DuckDuckGo search fallback (no API key required) |
| `requests` + `beautifulsoup4` | Page extraction fallback |
| `pydantic` | Structured data models with validation |
| `python-dotenv` | `.env` loading |
