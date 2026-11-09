"""
Creates the LLM client chosen in .env:

    LLM_PROVIDER=mistral     -> Mistral API (MISTRAL_API_KEY)
    LLM_PROVIDER=kiconnect   -> KI:connect.nrw / RWTHgpt (KICONNECT_API_KEY,
                                KICONNECT_BASE_URL)

In both cases the model names come from MISTRAL_MODEL, MISTRAL_VISION_MODEL,
TITLE_MODEL and TRANSLATION_MODEL (the names are historical — with
kiconnect put KI:connect model ids there, e.g. mistral-small-4-119b-2603).
"""

from llm.base import BaseLLM
from settings import settings


def create_llm(model: str | None = None) -> BaseLLM:
    provider = (getattr(settings, "LLM_PROVIDER", "mistral") or "mistral").strip().lower()

    if provider == "kiconnect":
        from llm.openai_compat import OpenAICompatLLM
        return OpenAICompatLLM(
            api_key=settings.KICONNECT_API_KEY,
            base_url=settings.KICONNECT_BASE_URL,
            model=model,
        )

    if provider == "mistral":
        from llm.mistral import MistralLLM
        return MistralLLM(api_key=settings.MISTRAL_API_KEY, model=model)

    raise ValueError(f"Unknown LLM_PROVIDER {provider!r} (use 'mistral' or 'kiconnect')")
