import os
from typing import List, Dict, Any
from .base import BaseLLM
from mistralai.client import Mistral
from config import Config

class MistralLLM(BaseLLM):
    def __init__(self, api_key: str | None = None):
        """
        Initializing the Mistral client
        """
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")

        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY is not set")

        self.client = Mistral(api_key=self.api_key)

        self.model = Config.MODEL_NAME

    def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any
    ) -> str:
        """
        Sends a request to the Mistral API
        """
        response = self.client.chat.complete(
            model=self.model,
            messages=messages,
            **kwargs
        )

        return response.choices[0].message.content
