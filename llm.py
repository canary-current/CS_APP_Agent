"""
Thin LLM abstraction — supports Anthropic (Claude) and DeepSeek.
Select the provider via the LLM_PROVIDER env var ("anthropic" or "deepseek").
"""

from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()

# DeepSeek models
_DEEPSEEK_CHAT  = "deepseek-chat"        # DeepSeek-V3 — fast, cheap
_DEEPSEEK_REASON = "deepseek-reasoner"   # DeepSeek-R1 — for complex reasoning

# Anthropic models
_CLAUDE_FAST = "claude-haiku-4-5-20251001"


def complete(system: str, user: str, *, max_tokens: int = 1024) -> str:
    """
    Send a system + user prompt to the configured LLM and return the text reply.
    """
    if _PROVIDER == "anthropic":
        return _anthropic_complete(system, user, max_tokens)
    return _deepseek_complete(system, user, max_tokens)


def _deepseek_complete(system: str, user: str, max_tokens: int) -> str:
    from openai import OpenAI
    from config import DEEPSEEK_API_KEY

    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )
    resp = client.chat.completions.create(
        model=_DEEPSEEK_CHAT,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return resp.choices[0].message.content.strip()


def _anthropic_complete(system: str, user: str, max_tokens: int) -> str:
    from anthropic import Anthropic
    from config import get_anthropic_api_key

    client = Anthropic(api_key=get_anthropic_api_key())
    msg = client.messages.create(
        model=_CLAUDE_FAST,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()
