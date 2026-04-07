from typing import Any, AsyncIterator
from mistralai.client import Mistral
from api.llm.base import BaseLLM
from api.settings import settings

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

        self.client = Mistral(api_key=self.api_key)

    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any
    ) -> str:
        """
        Send a request to the Mistral API and return the full response text.
        """

        response = self.client.chat.complete(
            model=self.model,
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
        messages: list[dict[str, str]],
        **kwargs: Any
    ) -> AsyncIterator[str]:
        """
        Stream response chunks from the Mistral API.
        For now this is a placeholder implementation.
        """

        full_response = await self.chat(messages, **kwargs)

        yield full_response
        