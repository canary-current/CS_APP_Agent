"""
CS Application Agent — interactive REPL.

Orchestrates three tools via any supported LLM provider (see llm.py):
  search_program          → find the official admissions page
  collect_program_info    → scrape deadlines, language reqs, funding, courses
  fetch_application_examples → find SOPs, personal statements, admission stats

Run:
  python agent.py
"""

from __future__ import annotations
import json
import shutil
import sys
import textwrap
from pathlib import Path

import llm
from models import ProgramInfo, ApplicationExample
from tools.search import search_program, TOOL_SCHEMA as _SEARCH
from tools.collect import collect_program_info, TOOL_SCHEMA as _COLLECT
from tools.examples import fetch_application_examples, TOOL_SCHEMA as _EXAMPLES
from tools.export import save_program_md
import checker

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def _dispatch(name: str, args: dict) -> str:
    """Call the named tool and return its result as a JSON string."""
    try:
        if name == "search_program":
            result = search_program(**args)
            return json.dumps(result.model_dump(), ensure_ascii=False)

        if name == "collect_program_info":
            result = collect_program_info(**args)
            return json.dumps(result.model_dump(), ensure_ascii=False)

        if name == "fetch_application_examples":
            results = fetch_application_examples(**args)
            return json.dumps([r.model_dump() for r in results], ensure_ascii=False)

        return json.dumps({"error": f"unknown tool: {name}"})

    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_label(name: str, args: dict) -> str:
    """Human-readable one-liner shown while a tool runs."""
    if name == "search_program":
        return f"search  {args.get('school')} — {args.get('program')}"
    if name == "collect_program_info":
        return f"collect {args.get('url', '')[:70]}"
    if name == "fetch_application_examples":
        return f"examples {args.get('school')} — {args.get('program')}"
    return name


# ---------------------------------------------------------------------------
# Schema conversion  (Anthropic format → OpenAI/DeepSeek format)
# ---------------------------------------------------------------------------

def _to_openai(schema: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema["description"],
            "parameters": schema["input_schema"],
        },
    }


_TOOLS = [_to_openai(s) for s in (_SEARCH, _COLLECT, _EXAMPLES)]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = textwrap.dedent("""\
    You are a knowledgeable assistant helping a student apply to CS graduate programs.

    You have three tools:
    • search_program             — find a program's official admissions page
    • collect_program_info       — extract structured program details
    • fetch_application_examples — find real SOPs, personal statements, admission stats

    Workflow:
    1. Call search_program to get the official URL.
    2. Call collect_program_info with that URL.
    3. Call fetch_application_examples for essay and stats context.
    4. Present a complete answer using the format below.

    IMPORTANT — school and program names:
    • Always pass the full official institution name (e.g. "Hong Kong University
      of Science and Technology", never "HKUST"). Resolve abbreviations before
      calling any tool.
    • When calling collect_program_info on supplementary pages (tuition, language
      requirements, etc.), always pass the same school and program values as the
      original query — never use a page title as the program name.

    ─── REQUIRED RESPONSE FORMAT ───────────────────────────────────────────
    Every response about a specific program MUST contain all of these sections.
    Write "Not available" for any field genuinely absent after searching.

    ## [School] — [Program]

    ### Deadline
    <application deadline>

    ### Language Requirements
    - TOEFL minimum: <score or Not available>
    - IELTS minimum: <score or Not available>
    - Other accepted tests: <e.g. "Duolingo: 120+" or "None listed">
    - English-institution waiver: <Yes / No / Not specified>
    - Notes: <any extra detail, or omit>

    ### Tuition & Funding
    - Tuition (local/domestic): <amount with currency, or Not available>
    - Tuition (international/non-local): <amount with currency, or Not available>
    - Funding: <RA/TA/fellowship/stipend details>

    ### Program Length
    <length in years>

    ### Courses
    <list of courses, or "Not listed on official page">

    ### Application Examples & Admission Stats
    <SOP insights, admission rate, typical GPA/GRE, tips>
    ────────────────────────────────────────────────────────────────────────

    Never omit a section. Never guess — use actual data from the tools.
""")

# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

def _print_progress(info: ProgramInfo) -> None:
    """Print a one-line field-completeness bar after a collect_program_info call."""
    total = len(checker.REQUIRED)
    missing_shorts: list[str] = []
    bar = ""
    for spec in checker.REQUIRED:
        if spec.is_missing(info):
            bar += "\033[33m░\033[0m"   # yellow empty block
            missing_shorts.append(spec.short or spec.label.split()[0])
        else:
            bar += "\033[32m█\033[0m"   # green filled block

    filled = total - len(missing_shorts)
    suffix = (
        "  missing: " + " · ".join(missing_shorts)
        if missing_shorts
        else "  \033[32mall fields found\033[0m"
    )
    print(f"  [{bar}] {filled}/{total}{suffix}", flush=True)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def _run_turn(messages: list[dict], user_input: str) -> str:
    """
    Append the user message, drive the tool-use loop to completion,
    and return the final assistant reply.
    """
    messages.append({"role": "user", "content": user_input})

    while True:
        text, tool_calls, assistant_msg = llm.chat_with_tools(messages, _TOOLS)
        messages.append(assistant_msg)

        if tool_calls is not None:
            for tc in tool_calls:
                print(f"\n  \033[36m⚙ {_tool_label(tc['name'], tc['args'])}\033[0m",
                      flush=True)
                result_str = _dispatch(tc["name"], tc["args"])
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str,
                })
                if tc["name"] == "collect_program_info":
                    try:
                        data = json.loads(result_str)
                        if "error" not in data:
                            _print_progress(ProgramInfo(**data))
                    except Exception:
                        pass

        else:
            return text or ""


# ---------------------------------------------------------------------------
# Completeness checker
# ---------------------------------------------------------------------------

def _collect_infos_from_turn(messages: list[dict], turn_start: int) -> list[ProgramInfo]:
    """
    Extract every ProgramInfo that collect_program_info returned during this turn.
    Correlates tool_call_ids so we only look at the right tool.
    """
    call_id_to_name: dict[str, str] = {}
    for msg in messages[turn_start:]:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                call_id_to_name[tc["id"]] = tc["function"]["name"]

    infos: list[ProgramInfo] = []
    for msg in messages[turn_start:]:
        if msg.get("role") == "tool":
            if call_id_to_name.get(msg.get("tool_call_id", "")) == "collect_program_info":
                try:
                    data = json.loads(msg["content"])
                    if "error" not in data:
                        infos.append(ProgramInfo(**data))
                except Exception:
                    pass
    return infos


def _completeness_followup(
    messages: list[dict],
    turn_start: int,
) -> str | None:
    """
    Inspect every collect_program_info result from the latest turn.
    If any required fields are missing, inject one follow-up turn automatically
    and return its reply. Returns None if everything is complete.
    """
    infos = _collect_infos_from_turn(messages, turn_start)
    if not infos:
        return None

    prompts: list[str] = []
    total_missing = 0
    for info in infos:
        missing = checker.missing_fields(info)
        if missing:
            total_missing += len(missing)
            prompts.append(checker.follow_up_prompt(info, missing))

    if not prompts:
        return None

    print(
        f"\n  \033[33m⚠ Completeness check: {total_missing} required field(s) missing"
        f" — auto-searching…\033[0m",
        flush=True,
    )
    return _run_turn(messages, "\n\n".join(prompts))


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------

def _scan_tool_results(
    messages: list[dict],
    turn_start: int,
) -> tuple[dict[tuple, ProgramInfo], dict[tuple, list[ApplicationExample]]]:
    """
    Walk messages[turn_start:] and return:
      infos    — {(school, program): ProgramInfo}   (last collect call wins)
      examples — {(school, program): [ApplicationExample]}
    """
    call_id_to_name: dict[str, str] = {}
    for msg in messages[turn_start:]:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                call_id_to_name[tc["id"]] = tc["function"]["name"]

    infos: dict[tuple, ProgramInfo] = {}
    examples: dict[tuple, list[ApplicationExample]] = {}

    for msg in messages[turn_start:]:
        if msg.get("role") != "tool":
            continue
        tool_name = call_id_to_name.get(msg.get("tool_call_id", ""))
        try:
            data = json.loads(msg["content"])
        except Exception:
            continue

        if tool_name == "collect_program_info" and "error" not in data:
            info = ProgramInfo(**data)
            infos[(info.school, info.program)] = info

        elif tool_name == "fetch_application_examples" and isinstance(data, list):
            for item in data:
                ex = ApplicationExample(**item)
                examples.setdefault((ex.school, ex.program), []).append(ex)

    return infos, examples


def _export_results(messages: list[dict], turn_start: int) -> None:
    """Save every collected program to schools/{school}/{program}.md."""
    infos, examples = _scan_tool_results(messages, turn_start)
    for key, info in infos.items():
        path = save_program_md(info, examples.get(key, []))
        rel = path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path
        print(f"\n  \033[32m📄 Saved → {rel}\033[0m", flush=True)


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

_BANNER = """
╔══════════════════════════════════════════════╗
║        CS Graduate Application Agent         ║
║  Ask about any CS program — I'll research it ║
║  /clear  — wipe cache & output files         ║
║  exit    — quit                              ║
╚══════════════════════════════════════════════╝
"""

_ROOT = Path(__file__).parent
_CLEAR_DIRS = {"cache": _ROOT / "cache", "schools": _ROOT / "schools"}


def _do_clear(targets: list[str]) -> None:
    for name in targets:
        path = _CLEAR_DIRS[name]
        if not path.exists():
            print(f"  {name}/  — already empty")
            continue
        count = sum(1 for f in path.rglob("*") if f.is_file())
        shutil.rmtree(path)
        path.mkdir()
        print(f"  \033[32m✓ {name}/  — removed {count} file(s)\033[0m")
    print()


def main() -> None:
    messages: list[dict] = [{"role": "system", "content": _SYSTEM}]

    print(_BANNER)

    ok, hint = llm.validate_config()
    if not ok:
        print(f"\033[31m  Configuration error\033[0m\n")
        for line in hint.splitlines():
            print(f"  {line}")
        print(f"\n  Copy .env.example → .env and fill in the key, then re-run.\n")
        sys.exit(1)

    print(f"  Provider: {llm.provider_label()}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("Bye!")
            sys.exit(0)

        cmd = user_input.lower()
        if cmd == "/clear":
            _do_clear(list(_CLEAR_DIRS))
            continue
        if cmd == "/clear cache":
            _do_clear(["cache"])
            continue
        if cmd == "/clear schools":
            _do_clear(["schools"])
            continue

        print()
        turn_start = len(messages)
        try:
            reply = _run_turn(messages, user_input)
        except Exception as exc:
            print(f"\033[31mError: {exc}\033[0m")
            continue

        try:
            followup = _completeness_followup(messages, turn_start)
        except Exception as exc:
            print(f"\033[33m⚠ Completeness check error: {exc}\033[0m")
            followup = None

        print(f"\nAgent:\n{followup if followup else reply}\n")

        try:
            _export_results(messages, turn_start)
        except Exception as exc:
            print(f"\033[33m⚠ Export error: {exc}\033[0m")


if __name__ == "__main__":
    main()
