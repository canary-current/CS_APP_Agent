import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


TAVILY_API_KEY: str | None = os.getenv("TAVILY_API_KEY") or None
DEEPSEEK_API_KEY: str = _require("DEEPSEEK_API_KEY")


def get_anthropic_api_key() -> str:
    return _require("ANTHROPIC_API_KEY")
