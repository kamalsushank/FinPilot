"""Shared Gemini client. No API key is hard-coded; set GEMINI_API_KEY in .env."""
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def gemini_enabled() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


@lru_cache(maxsize=1)
def get_gemini_client():
    if not gemini_enabled():
        return None
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def get_model_name() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def generate_text(prompt: str, use_google_search: bool = False) -> tuple[str, list[dict]]:
    """Return (text, source links). If Google Search grounding is enabled, extract citations."""
    client = get_gemini_client()
    if client is None:
        raise RuntimeError("Gemini is not configured. Set GEMINI_API_KEY in your .env file.")
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=(
            "You are a careful assistant for a personal finance learning project. "
            "Never invent balances, current interest rates, eligibility rules, or guaranteed returns. "
            "Distinguish verified facts from uncertainty. Do not claim to be a licensed financial adviser."
        ),
        tools=[types.Tool(google_search=types.GoogleSearch())] if use_google_search else None,
        temperature=0.2,
    )
    response = client.models.generate_content(
        model=get_model_name(),
        contents=prompt,
        config=config,
    )
    text = (getattr(response, "text", None) or "").strip()
    sources: list[dict] = []
    try:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            metadata = getattr(candidate, "grounding_metadata", None)
            chunks = getattr(metadata, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None) if web else None
                title = getattr(web, "title", None) if web else None
                if uri and all(item["url"] != uri for item in sources):
                    sources.append({"title": title or uri, "url": uri})
    except Exception:
        # The text response remains usable even if SDK metadata shape changes.
        pass
    if not text:
        raise RuntimeError("Gemini returned an empty response.")
    return text, sources
