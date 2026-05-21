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
import sys
import textwrap
from pathlib import Path

import llm
from models import ProgramInfo, ApplicationExample, LanguageRequirements, Tuition
from tools.search import search_program, TOOL_SCHEMA as _SEARCH
from tools.collect import collect_program_info, TOOL_SCHEMA as _COLLECT
from tools.examples import fetch_application_examples, TOOL_SCHEMA as _EXAMPLES
from tools.export import save_program_md
from clean import CLEAR_DIRS, clear_dir
import checker
import status

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

    Workflow (per program):
    1. Call search_program to get the official URL.
    2. Call collect_program_info with that URL.
    3. Call fetch_application_examples for essay and stats context.
    4. Present a complete answer using the format below.

    IMPORTANT — one program at a time:
    • If the user asks about multiple programs (e.g. "MIT and Stanford CS PhD"),
      research them STRICTLY SEQUENTIALLY. Complete steps 1–4 for the first
      program — including the final written answer — BEFORE issuing any tool
      call for the next program.
    • Never interleave tool calls for different (school, program) pairs.
    • Emit exactly one tool call per response; wait for its result before
      deciding the next step.

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

def _save_now(info: ProgramInfo, examples: list[ApplicationExample] | None = None) -> None:
    """Write the Markdown file for one program immediately, merging with any
    prior in-turn collect result so multiple collect calls produce one file
    with the union of fields. Logs the saved path so the user always sees it."""
    key = (info.school, info.program)
    prior = _turn_infos.get(key)
    if prior is not None:
        info = _merge_program_infos(prior, info)
    _turn_infos[key] = info
    if examples is not None:
        _turn_examples.setdefault(key, []).extend(examples)
    try:
        path = save_program_md(info, _turn_examples.get(key, []))
    except Exception as exc:
        status.emit(f"  \033[33m⚠ Save error for {info.school} — {info.program}: {exc}\033[0m")
        return
    # Announce the file only the first time this turn — silent re-saves
    # happen when later collect/examples calls add more data.
    if key not in _turn_announced:
        _turn_announced.add(key)
        rel = path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path
        status.emit(f"  \033[32m📄 Saved → {rel}\033[0m")


# Turn-scoped accumulators reset at the start of each REPL turn.
_turn_infos: dict[tuple, ProgramInfo] = {}
_turn_examples: dict[tuple, list[ApplicationExample]] = {}
_turn_announced: set[tuple] = set()


def _reset_turn_state() -> None:
    _turn_infos.clear()
    _turn_examples.clear()
    _turn_announced.clear()


def _progress_line(info: ProgramInfo | None = None) -> str:
    """Build the field-completeness bar string.

    With info=None, every field is treated as missing (the "pre-collect"
    state shown at the start of each turn so the user sees the bar
    structure immediately instead of a placeholder).
    """
    total = len(checker.REQUIRED)
    missing_shorts: list[str] = []
    bar = ""
    for spec in checker.REQUIRED:
        if info is None or spec.is_missing(info):
            bar += "\033[33m░\033[0m"   # yellow empty block
            missing_shorts.append(spec.short or spec.label.split()[0])
        else:
            bar += "\033[32m█\033[0m"   # green filled block

    filled = total - len(missing_shorts)
    if missing_shorts:
        suffix = "  missing: " + " · ".join(missing_shorts)
    else:
        suffix = "  \033[32mall fields found\033[0m"
    return f" \033[36m●\033[0m  Progress  [{bar}] {filled}/{total}{suffix}"


def _render_progress(info: ProgramInfo) -> None:
    """Render the field-completeness bar on the bottom status line."""
    status.set(bottom=_progress_line(info))


def _tool_status_top(name: str, args: dict) -> str:
    """One-line description of the current tool call for the top status row."""
    if name == "search_program":
        target = f"{args.get('school', '')} — {args.get('program', '')}"
        return f" \033[36m▸\033[0m  Searching: {target}"
    if name == "collect_program_info":
        url = status.shorten_url(args.get("url", ""))
        return f" \033[36m▸\033[0m  Reading:   {url}"
    if name == "fetch_application_examples":
        target = f"{args.get('school', '')} — {args.get('program', '')}"
        return f" \033[36m▸\033[0m  Examples:  {target}"
    return f" \033[36m▸\033[0m  Running:   {name}"


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

_MAX_TOOL_ITERATIONS = 12  # safety cap; a normal turn uses 3–6 tool calls


def _run_turn(messages: list[dict], user_input: str) -> str:
    """
    Append the user message, drive the tool-use loop to completion,
    and return the final assistant reply.
    """
    messages.append({"role": "user", "content": user_input})

    for _ in range(_MAX_TOOL_ITERATIONS):
        text, tool_calls, assistant_msg = llm.chat_with_tools(messages, _TOOLS)
        messages.append(assistant_msg)

        if tool_calls is not None:
            for tc in tool_calls:
                status.set(top=_tool_status_top(tc["name"], tc["args"]))
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
                            info = ProgramInfo(**data)
                            _render_progress(info)
                            _save_now(info)
                    except Exception as exc:
                        status.emit(f"  \033[33m⚠ Save skipped: {exc}\033[0m")

                elif tc["name"] == "fetch_application_examples":
                    try:
                        data = json.loads(result_str)
                        if isinstance(data, list) and data:
                            new_exs = [ApplicationExample(**item) for item in data]
                            ex_key = (new_exs[0].school, new_exs[0].program)
                            if ex_key in _turn_infos:
                                # Re-save with newly available examples.
                                _save_now(_turn_infos[ex_key], new_exs)
                            else:
                                _turn_examples.setdefault(ex_key, []).extend(new_exs)
                    except Exception:
                        pass

        else:
            return text or ""

    status.emit(f"  \033[33m⚠ Reached max tool iterations ({_MAX_TOOL_ITERATIONS}); "
                f"forcing the model to produce a final answer.\033[0m")
    messages.append({
        "role": "user",
        "content": (
            f"You have used the tool budget for this turn. Stop calling tools and "
            f"provide the best final answer you can with the data already collected."
        ),
    })
    text, _, assistant_msg = llm.chat_with_tools(messages, tools=[])
    messages.append(assistant_msg)
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

    status.emit(
        f"  \033[33m⚠ Completeness check: {total_missing} required field(s) missing"
        f" — auto-searching…\033[0m"
    )
    return _run_turn(messages, "\n\n".join(prompts))


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------

def _merge_program_infos(base: ProgramInfo, extra: ProgramInfo) -> ProgramInfo:
    """Merge extra into base, filling missing fields without overwriting existing ones."""
    lr_b, lr_e = base.language_requirements, extra.language_requirements
    t_b, t_e   = base.tuition, extra.tuition
    return ProgramInfo(
        school=base.school,
        program=base.program,
        url=base.url,
        deadline=base.deadline if base.deadline is not None else extra.deadline,
        language_requirements=LanguageRequirements(
            toefl_min=lr_b.toefl_min if lr_b.toefl_min is not None else lr_e.toefl_min,
            ielts_min=lr_b.ielts_min if lr_b.ielts_min is not None else lr_e.ielts_min,
            english_institution_waiver=(
                lr_b.english_institution_waiver
                if lr_b.english_institution_waiver is not None
                else lr_e.english_institution_waiver
            ),
            other_tests=list({*lr_b.other_tests, *lr_e.other_tests}),
            notes=lr_b.notes or lr_e.notes,
        ),
        tuition=Tuition(
            local=t_b.local if t_b.local is not None else t_e.local,
            international=t_b.international if t_b.international is not None else t_e.international,
            notes=t_b.notes or t_e.notes,
        ),
        funding=base.funding or extra.funding,
        length_years=base.length_years if base.length_years is not None else extra.length_years,
        courses=list({*base.courses, *extra.courses}),
    )


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

def _do_clear(targets: list[str]) -> None:
    for name in targets:
        count = clear_dir(CLEAR_DIRS[name])
        if count < 0:
            print(f"  {name}/  — already empty")
        else:
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

    status.enable()

    while True:
        status.hide()
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            status.disable()
            print("\nBye!")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("Bye!")
            sys.exit(0)

        cmd = user_input.lower()
        if cmd == "/clear":
            _do_clear(list(CLEAR_DIRS))
            continue
        if cmd == "/clear cache":
            _do_clear(["cache"])
            continue
        if cmd == "/clear schools":
            _do_clear(["schools"])
            continue

        print()
        _reset_turn_state()
        status.set(
            top=" \033[36m▸\033[0m  Starting…",
            bottom=_progress_line(),
        )
        turn_start = len(messages)
        try:
            reply = _run_turn(messages, user_input)
        except Exception as exc:
            status.emit(f"\033[31mError: {exc}\033[0m")
            continue

        try:
            followup = _completeness_followup(messages, turn_start)
        except Exception as exc:
            status.emit(f"\033[33m⚠ Completeness check error: {exc}\033[0m")
            followup = None

        status.emit(f"\nAgent:\n{followup if followup else reply}\n")

        if not _turn_infos:
            status.emit("  \033[33mℹ No program data collected this turn — "
                        "nothing to save.\033[0m")

        # Hide the status block between turns — the next "You:" prompt
        # sits on a clean line at the visible bottom.
        status.hide()


if __name__ == "__main__":
    main()
