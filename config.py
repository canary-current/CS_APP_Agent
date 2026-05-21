import os
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY: str | None = os.getenv("TAVILY_API_KEY") or None
