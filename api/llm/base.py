from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

# NOTE: a message's "content" is either a plain string (text-only turn) or
# a list of Mistral-style content blocks, e.g.:
#   [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:..."}}]
# for turns that include an image attachment.
Message = dict[str, Any]


class BaseLLM(ABC):
    """
    Base interface for all LLM providers.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        **kwargs: Any
    ) -> str:
        """
        Generate a full response from the model.
        """
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        **kwargs: Any
    ) -> AsyncIterator[str]:
        """
        Stream partial response chunks from the model.
        """
        raise NotImplementedError
    