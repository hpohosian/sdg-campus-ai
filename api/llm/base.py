from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseLLM(ABC):
    """
    Abstract class for all LLM models.
    """
    
    def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any
    ) -> str:
        """
        The main method for generating a response.
        
        :param messages: list of messages (chat history)
        :return: model response (str)
        """
        pass