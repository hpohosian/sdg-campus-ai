"""
LLM provider for OpenAI-compatible APIs — used for KI:connect.nrw
(RWTHgpt, https://chat.kiconnect.nrw/api/v1), the university's LLM gateway.

Same interface as MistralLLM (BaseLLM), same retry/throttle behaviour, so
the rest of the backend does not know which provider it talks to. Switch
with LLM_PROVIDER in .env (see llm/factory.py).
"""

from typing import Any, AsyncIterator

from openai import AsyncOpenAI, BadRequestError

from llm.base import BaseLLM, Message
from llm.mistral import _with_retry
from settings import settings


class OpenAICompatLLM(BaseLLM):
    # Models that reject a custom temperature ("Only the default (1) value
    # is supported", e.g. gpt-6-luna on KI:connect since Nov 2026). Filled
    # on the first such error, so every later request leaves it out at once.
    _no_temperature: set[str] = set()

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str | None = None,
        vision_model: str | None = None,
    ):
        if not api_key:
            raise ValueError("API key for the OpenAI-compatible provider is not set (KICONNECT_API_KEY)")
        self.model = model or settings.MISTRAL_MODEL
        self.vision_model = vision_model or getattr(settings, "MISTRAL_VISION_MODEL", None) or self.model
        # max_retries=0: retries are done by _with_retry (same policy and
        # log lines as for Mistral, plus the client-side throttle).
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=120)

    @staticmethod
    def _contains_image(messages: list[Message]) -> bool:
        for m in messages:
            content = m.get("content") if isinstance(m, dict) else None
            if isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "image_url" for b in content
            ):
                return True
        return False

    def _resolve_model(self, messages: list[Message], explicit_model: str | None) -> str:
        if explicit_model:
            return explicit_model
        return self.vision_model if self._contains_image(messages) else self.model

    async def _create(self, model: str, messages: list[Message], what: str, **kwargs: Any):
        """
        One API call with retry. If the model rejects "temperature", the
        call is repeated once without it (the answer is then sampled with
        the model's default temperature, which is fine for our use).
        """
        if model in self._no_temperature:
            kwargs.pop("temperature", None)

        def call(params: dict):
            return _with_retry(
                lambda: self.client.chat.completions.create(model=model, messages=messages, **params),
                what,
                model,
            )

        try:
            return await call(kwargs)
        except BadRequestError as e:
            if "temperature" not in kwargs or "temperature" not in str(e).lower():
                raise
            print(f"[llm] {model} does not accept temperature={kwargs['temperature']}, using its default")
            self._no_temperature.add(model)
            kwargs.pop("temperature")
            return await call(kwargs)

    async def chat(self, messages: list[Message], **kwargs: Any) -> str:
        model = self._resolve_model(messages, kwargs.pop("model", None))
        response = await self._create(model, messages, "chat", **kwargs)
        if not response.choices:
            raise ValueError("No response choices returned from the LLM API")
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response content returned from the LLM API")
        return content

    async def stream(self, messages: list[Message], **kwargs: Any) -> AsyncIterator[str]:
        model = self._resolve_model(messages, kwargs.pop("model", None))
        stream = await self._create(model, messages, "stream", stream=True, **kwargs)
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
