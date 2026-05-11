from chatbot.prompts import SYSTEM_PROMPT
from llm.base import BaseLLM

class AIService:
    def __init__(self, llm: BaseLLM):
        self.llm = llm


    async def generate_response(self, messages):
        # 1. format DB messages → LLM format
        formatted = self._format(messages)

        # 2. add system prompt
        formatted.insert(0, {
            "role": "system",
            "content": self._system_prompt()
        })

        # 3. call model
        return await self.llm.chat(formatted)


    def _format(self, messages):
        return [
            {
                "role": m.role,
                "content": m.content
            }
            for m in messages
        ]


    def _system_prompt(self):
        return SYSTEM_PROMPT
    