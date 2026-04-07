from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

class BaseLLM(ABC):
    """
    Base interface for all LLM providers.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any
    ) -> str:
        """
        Generate a full response from the model.
        """
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any
    ) -> AsyncIterator[str]:
        """
        Stream partial response chunks from the model.
        """
        raise NotImplementedError
    