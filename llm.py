"""
LLM abstraction — supports any provider via preset or custom configuration.

Provider selection (in order of precedence):
  1. LLM_PROVIDER=<preset>   — one of the named presets below
  2. LLM_BASE_URL + LLM_API_KEY — arbitrary OpenAI-compatible endpoint
  3. Default: deepseek

Per-provider overrides (all optional):
  LLM_API_KEY   — overrides the preset's default key env var
  LLM_BASE_URL  — overrides the preset's base URL (openai-type only)
  LLM_MODEL     — overrides the preset's default model
"""

from __future__ import annotations
import json
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Provider presets
# ---------------------------------------------------------------------------

_PRESETS: dict[str, dict] = {
    "deepseek":  {"type": "openai",    "url": "https://api.deepseek.com",
                  "model": "deepseek-chat",                     "key_env": "DEEPSEEK_API_KEY"},
    "openai":    {"type": "openai",    "url": "https://api.openai.com/v1",
                  "model": "gpt-4o-mini",                       "key_env": "OPENAI_API_KEY"},
    "anthropic": {"type": "anthropic",
                  "model": "claude-haiku-4-5-20251001",         "key_env": "ANTHROPIC_API_KEY"},
    "gemini":    {"type": "openai",    "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                  "model": "gemini-2.0-flash",                  "key_env": "GEMINI_API_KEY"},
    "groq":      {"type": "openai",    "url": "https://api.groq.com/openai/v1",
                  "model": "llama-3.3-70b-versatile",           "key_env": "GROQ_API_KEY"},
    "mistral":   {"type": "openai",    "url": "https://api.mistral.ai/v1",
                  "model": "mistral-small-latest",              "key_env": "MISTRAL_API_KEY"},
    "xai":       {"type": "openai",    "url": "https://api.x.ai/v1",
                  "model": "grok-3-mini",                       "key_env": "XAI_API_KEY"},
    "together":  {"type": "openai",    "url": "https://api.together.xyz/v1",
                  "model": "meta-llama/Llama-3-70b-chat-hf",   "key_env": "TOGETHER_API_KEY"},
    "ollama":    {"type": "openai",    "url": "http://localhost:11434/v1",
                  "model": "llama3.2",                          "key_env": "OLLAMA_API_KEY"},
}


def _resolve_config() -> dict:
    """Build the active provider config from env vars, applying any overrides."""
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    cfg = dict(_PRESETS.get(provider, {"type": "openai", "url": "", "model": "", "key_env": "LLM_API_KEY"}))

    if os.getenv("LLM_API_KEY"):
        cfg["key_env"] = "LLM_API_KEY"
    if os.getenv("LLM_BASE_URL"):
        cfg["url"] = os.environ["LLM_BASE_URL"]
    if os.getenv("LLM_MODEL"):
        cfg["model"] = os.environ["LLM_MODEL"]

    return cfg


def _get_api_key(cfg: dict) -> str:
    key = os.getenv(cfg.get("key_env", "")) or os.getenv("LLM_API_KEY") or ""
    if not key and cfg.get("url", "").startswith("http://localhost"):
        key = "ollama"  # local server, no auth required
    if not key:
        raise RuntimeError(
            f"No API key found. Set {cfg['key_env']} (or LLM_API_KEY) in your .env file."
        )
    return key


def provider_label() -> str:
    """Human-readable identifier for the active provider, shown in the startup banner."""
    provider = os.getenv("LLM_PROVIDER", "").strip().lower() or "?"
    cfg = _resolve_config()
    return f"{provider} / {cfg.get('model', 'unknown')}"


def validate_config() -> tuple[bool, str]:
    """
    Check that LLM_PROVIDER is set and its API key is configured.

    Returns:
        (True, "")              — config is valid, ready to go.
        (False, hint_message)   — something is missing; hint tells the user what to set.
    """
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()

    presets = ", ".join(sorted(_PRESETS))

    if not provider:
        return False, (
            "LLM_PROVIDER is not set in your .env file.\n"
            "\n"
            "Add these lines to .env:\n"
            "\n"
            "  LLM_PROVIDER=<provider>\n"
            "  <PROVIDER>_API_KEY=<your-key>\n"
            "\n"
            f"Supported presets: {presets}\n"
            "\n"
            "For a custom OpenAI-compatible endpoint, use:\n"
            "  LLM_PROVIDER=<any-name>\n"
            "  LLM_BASE_URL=<base-url>\n"
            "  LLM_API_KEY=<your-key>\n"
            "  LLM_MODEL=<model-name>"
        )

    if provider not in _PRESETS and not (
        os.getenv("LLM_BASE_URL") and os.getenv("LLM_MODEL")
    ):
        return False, (
            f"Unknown provider '{provider}'.\n"
            "\n"
            f"Supported presets: {presets}\n"
            "\n"
            "To use a custom endpoint instead, also set:\n"
            "  LLM_BASE_URL=<base-url>\n"
            "  LLM_MODEL=<model-name>\n"
            "  LLM_API_KEY=<your-key>"
        )

    cfg = _resolve_config()
    is_local = cfg.get("url", "").startswith("http://localhost")
    key = os.getenv(cfg.get("key_env", "")) or os.getenv("LLM_API_KEY") or ""

    if key or is_local:
        return True, ""

    key_env = cfg.get("key_env", "LLM_API_KEY")
    return False, (
        f"No API key found for provider '{provider}'.\n"
        f"\n"
        f"Add this to your .env file:\n"
        f"\n"
        f"  {key_env}=<your-key>"
    )


# ---------------------------------------------------------------------------
# complete() — single-turn extraction calls (no tool use)
# ---------------------------------------------------------------------------

def complete(system: str, user: str, *, max_tokens: int = 1024) -> str:
    """Send a system + user prompt and return the text reply."""
    cfg = _resolve_config()
    key = _get_api_key(cfg)
    if cfg["type"] == "anthropic":
        return _anthropic_complete(system, user, max_tokens, key, cfg["model"])
    return _openai_complete(system, user, max_tokens, key, cfg)


def _openai_complete(system: str, user: str, max_tokens: int, api_key: str, cfg: dict) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=cfg.get("url") or None)
    resp = client.chat.completions.create(
        model=cfg["model"],
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return resp.choices[0].message.content.strip()


def _anthropic_complete(system: str, user: str, max_tokens: int, api_key: str, model: str) -> str:
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()


# ---------------------------------------------------------------------------
# chat_with_tools() — agent tool-calling loop
# ---------------------------------------------------------------------------

def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    *,
    max_tokens: int = 4096,
) -> tuple[str | None, list[dict] | None, dict]:
    """
    Send a conversation (OpenAI-format, including system message) to the LLM.

    Args:
        messages: OpenAI-format message list (system message may be first).
        tools:    OpenAI-format tool schemas.

    Returns:
        (text, None, assistant_msg)       — model returned a text response.
        (None, tool_calls, assistant_msg) — model wants to invoke tools.

    assistant_msg is the complete dict to append to the message history;
    it may include provider-specific fields (e.g. reasoning_content for
    DeepSeek thinking models) that must be echoed back on the next turn.
    tool_calls format: [{"id": str, "name": str, "args": dict}, ...]
    """
    cfg = _resolve_config()
    key = _get_api_key(cfg)
    if cfg["type"] == "anthropic":
        return _anthropic_chat_with_tools(messages, tools, max_tokens, key, cfg["model"])
    return _openai_chat_with_tools(messages, tools, max_tokens, key, cfg)


def _openai_chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
    api_key: str,
    cfg: dict,
) -> tuple[str | None, list[dict] | None, dict]:
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=cfg.get("url") or None)
    response = client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        tools=tools,
        tool_choice="auto",
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    msg = choice.message

    if choice.finish_reason == "tool_calls":
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
        # Preserve reasoning_content for thinking-mode models (e.g. DeepSeek-R1,
        # deepseek-v4-pro) — the API requires it be echoed back on the next turn.
        if getattr(msg, "reasoning_content", None):
            assistant_msg["reasoning_content"] = msg.reasoning_content

        tool_calls = [
            {"id": tc.id, "name": tc.function.name, "args": json.loads(tc.function.arguments)}
            for tc in msg.tool_calls
        ]
        return None, tool_calls, assistant_msg

    assistant_msg = {"role": "assistant", "content": msg.content or ""}
    if getattr(msg, "reasoning_content", None):
        assistant_msg["reasoning_content"] = msg.reasoning_content
    return (msg.content or ""), None, assistant_msg


# --- Anthropic message format conversion ------------------------------------

def _to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Convert OpenAI-format message list to (system_text, anthropic_messages).

    Tool results (role="tool") are batched into a single user message with
    tool_result content blocks, as required by the Anthropic API.
    """
    system = ""
    result: list[dict] = []
    pending_results: list[dict] = []

    for msg in messages:
        role = msg.get("role")

        if role == "system":
            system = msg.get("content", "")
            continue

        if role != "tool" and pending_results:
            result.append({"role": "user", "content": pending_results})
            pending_results = []

        if role == "user":
            result.append({"role": "user", "content": msg["content"]})

        elif role == "assistant":
            tcs = msg.get("tool_calls")
            if tcs:
                blocks: list[dict] = []
                if msg.get("content"):
                    blocks.append({"type": "text", "text": msg["content"]})
                for tc in tcs:
                    args = tc["function"]["arguments"]
                    if isinstance(args, str):
                        args = json.loads(args)
                    blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": args,
                    })
                result.append({"role": "assistant", "content": blocks})
            else:
                result.append({"role": "assistant", "content": msg.get("content", "")})

        elif role == "tool":
            pending_results.append({
                "type": "tool_result",
                "tool_use_id": msg["tool_call_id"],
                "content": msg["content"],
            })

    if pending_results:
        result.append({"role": "user", "content": pending_results})

    return system, result


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-format tool schemas to Anthropic tool schemas."""
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "input_schema": t["function"]["parameters"],
        }
        for t in tools
    ]


def _anthropic_chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
    api_key: str,
    model: str,
) -> tuple[str | None, list[dict] | None]:
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    system, anthropic_messages = _to_anthropic_messages(messages)
    anthropic_tools = _to_anthropic_tools(tools)

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        tools=anthropic_tools,
        messages=anthropic_messages,
    )

    if response.stop_reason == "tool_use":
        tool_calls = [
            {"id": b.id, "name": b.name, "args": b.input}
            for b in response.content
            if b.type == "tool_use"
        ]
        # Build an OpenAI-format assistant message so the history stays consistent.
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        assistant_msg = {
            "role": "assistant",
            "content": "".join(text_blocks),
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
                for tc in tool_calls
            ],
        }
        return None, tool_calls, assistant_msg

    text = "".join(b.text for b in response.content if hasattr(b, "text"))
    return text.strip() or "", None, {"role": "assistant", "content": text.strip() or ""}
