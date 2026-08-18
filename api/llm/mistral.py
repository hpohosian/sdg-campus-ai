from typing import Any, AsyncIterator
from mistralai.client import Mistral
from llm.base import BaseLLM, Message
from settings import settings

# Fallback if MISTRAL_VISION_MODEL isn't set in settings/.env yet — Pixtral
# as a standalone model line has been deprecated by Mistral; vision is now
# folded into their regular chat models. mistral-small-latest is Mistral's
# own default in their vision docs examples. Override via
# settings.MISTRAL_VISION_MODEL if you want mistral-medium-2508 /
# mistral-large-2512 for higher accuracy on harder images.
_DEFAULT_VISION_MODEL = "mistral-small-latest"


class MistralLLM(BaseLLM):
    """
    Mistral implementation of the BaseLLM interface.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None
    ):
        self.api_key = api_key or settings.MISTRAL_API_KEY

        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY is not set")

        self.model = model or settings.MISTRAL_MODEL
        self.vision_model = getattr(settings, "MISTRAL_VISION_MODEL", None) or _DEFAULT_VISION_MODEL

        self.client = Mistral(api_key=self.api_key)

    @staticmethod
    def _contains_image(messages: list[Message]) -> bool:
        """True if any message content includes an image_url block."""
        for m in messages:
            content = m.get("content") if isinstance(m, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    return True
        return False

    def _resolve_model(self, messages: list[Message], explicit_model: str | None) -> str:
        if explicit_model:
            return explicit_model
        if self._contains_image(messages):
            return self.vision_model
        return self.model

    async def chat(
        self,
        messages: list[Message],
        **kwargs: Any
    ) -> str:
        """
        Send a request to the Mistral API and return the full response text.
        """
        model = self._resolve_model(messages, kwargs.pop("model", None))

        response = self.client.chat.complete(
            model=model,
            messages=messages,
            **kwargs
        )

        if not response.choices:
            raise ValueError("No response choices returned from Mistral API")

        content = response.choices[0].message.content

        if not content:
            raise ValueError("Empty response content returned from Mistral API")

        return content

    async def stream(
        self,
        messages: list[Message],
        **kwargs: Any
    ) -> AsyncIterator[str]:

        model = self._resolve_model(messages, kwargs.pop("model", None))

        stream = await self.client.chat.stream_async(
            model=model,
            messages=messages,
            **kwargs
        )

        async for chunk in stream:
            if chunk.data.choices:
                delta = chunk.data.choices[0].delta.content
                if delta:
                    yield delta
                    