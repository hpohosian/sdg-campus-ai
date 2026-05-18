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


    async def stream_response(self, messages):
        formatted = self._format(messages)

        formatted.insert(0, {
            "role": "system",
            "content": self._system_prompt()
        })

        async for token in self.llm.stream(formatted):
            yield token


    def _format(self, messages):
        # formatted = [
        #     {
        #         "role": m.role,
        #         "content": m.content
        #     }
        #     for m in messages
        # ]
        formatted = []

        for m in messages:
            formatted.append({
                "role": m["role"] if isinstance(m, dict) else m.role,
                "content": m["content"] if isinstance(m, dict) else m.content,
            })
        
        while formatted and formatted[-1]["role"] == "assistant":
            formatted.pop()

        return formatted


    def _system_prompt(self):
        return SYSTEM_PROMPT
    