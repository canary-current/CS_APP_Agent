"""
CS Application Agent — interactive REPL.

Orchestrates three tools via DeepSeek-V3 (OpenAI-compatible API):
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
from openai import OpenAI

from config import DEEPSEEK_API_KEY
from tools.search import search_program, TOOL_SCHEMA as _SEARCH
from tools.collect import collect_program_info, TOOL_SCHEMA as _COLLECT
from tools.examples import fetch_application_examples, TOOL_SCHEMA as _EXAMPLES

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
    • search_program          — find a program's official admissions page
    • collect_program_info    — extract deadlines, language requirements, funding, and courses
    • fetch_application_examples — find real SOPs, personal statements, and admission statistics

    Workflow:
    1. When asked about a program, call search_program first to get the URL.
    2. Pass that URL to collect_program_info for structured details.
    3. Call fetch_application_examples for essay examples and admission stats.
    4. Synthesise the results into a clear, well-organised answer.

    Always cite specific deadlines, score thresholds, and funding details when available.
    If a field was not found, say so honestly rather than guessing.
""")

# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def _run_turn(client: OpenAI, messages: list[dict], user_input: str) -> str:
    """
    Append the user message, drive the tool-use loop to completion,
    and return the final assistant reply.
    """
    messages.append({"role": "user", "content": user_input})

    while True:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=_TOOLS,
            tool_choice="auto",
            max_tokens=4096,
        )

        choice = response.choices[0]
        msg = choice.message

        if choice.finish_reason == "tool_calls":
            # Reconstruct as a plain dict so it serialises cleanly next turn.
            assistant_msg: dict = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
            messages.append(assistant_msg)

            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                print(f"\n  \033[36m⚙ {_tool_label(tc.function.name, args)}\033[0m",
                      flush=True)
                result_str = _dispatch(tc.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

        else:
            reply = msg.content or ""
            messages.append({"role": "assistant", "content": reply})
            return reply


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

_BANNER = """
╔══════════════════════════════════════════════╗
║        CS Graduate Application Agent         ║
║  Ask about any CS program — I'll research it ║
║  Type  'exit'  or  Ctrl-C  to quit           ║
╚══════════════════════════════════════════════╝
"""


def main() -> None:
    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )
    messages: list[dict] = [{"role": "system", "content": _SYSTEM}]

    print(_BANNER)

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

        print()
        try:
            reply = _run_turn(client, messages, user_input)
        except Exception as exc:
            print(f"\033[31mError: {exc}\033[0m")
            continue

        print(f"\nAgent: {reply}\n")


if __name__ == "__main__":
    main()
