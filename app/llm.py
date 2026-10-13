from functools import lru_cache
from typing import Any

from openai import OpenAI

from app.settings import LITELLM_API_KEY, LITELLM_BASE_URL


@lru_cache
def get_client() -> OpenAI:
    """Return the one client used for all text generation requests."""
    return OpenAI(base_url=LITELLM_BASE_URL, api_key=LITELLM_API_KEY, timeout=180.0, max_retries=0)


def complete(model: str, messages: list[dict[str, Any]], **kwargs: Any) -> str:
    response = get_client().chat.completions.create(model=model, messages=messages, **kwargs)
    return response.choices[0].message.content or ""
