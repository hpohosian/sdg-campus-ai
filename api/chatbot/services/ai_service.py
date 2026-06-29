from chatbot.prompts import RAG_SYSTEM_PROMPT, RAG_CONTEXT_TEMPLATE, NO_CONTEXT_PROMPT
from llm.base import BaseLLM
from rag.retriever import Retriever


class AIService:
    def __init__(self, llm: BaseLLM, retriever: Retriever = None):
        self.llm = llm
        self.retriever = retriever

    async def generate_response(self, messages, collection_name: str = None, course_ids: list[int] = None):
        user_query = self._get_last_user_message(messages)
        formatted = self._format(messages)
        system_prompt = await self._build_system_prompt(user_query, collection_name, course_ids)

        formatted.insert(0, {
            "role": "system",
            "content": system_prompt,
        })

        return await self.llm.chat(formatted)

    async def stream_response(self, messages, collection_name: str = None, course_ids: list[int] = None):
        user_query = self._get_last_user_message(messages)
        formatted = self._format(messages)
        system_prompt = await self._build_system_prompt(user_query, collection_name, course_ids)

        formatted.insert(0, {
            "role": "system",
            "content": system_prompt,
        })

        async for token in self.llm.stream(formatted):
            yield token

    async def _build_system_prompt(
        self,
        query: str,
        collection_name: str = None,
        course_ids: list[int] = None,
    ) -> str:
        """
        Priority:
        1. If a specific course is selected (collection_name) — search only that course.
        2. Otherwise, if the user has enrolled courses (course_ids) — search across all of them.
        3. Otherwise — plain LLM, no RAG context.
        """
        if not self.retriever or not query:
            return NO_CONTEXT_PROMPT

        if collection_name:
            context = self.retriever.retrieve_as_context(
                query=query,
                collection_name=collection_name,
                n_results=8,
            )
        elif course_ids:
            context = self.retriever.retrieve_as_context_global(
                query=query,
                course_ids=course_ids,
                n_results=8,
            )
        else:
            context = ""

        if not context:
            return NO_CONTEXT_PROMPT

        return RAG_SYSTEM_PROMPT + RAG_CONTEXT_TEMPLATE.format(context=context)

    def _get_last_user_message(self, messages) -> str:
        """Extract the last user message text for retrieval."""
        for msg in reversed(messages):
            role = msg["role"] if isinstance(msg, dict) else msg.role
            content = msg["content"] if isinstance(msg, dict) else msg.content
            if role == "user":
                return content
        return ""

    def _format(self, messages):
        formatted = []
        for m in messages:
            formatted.append({
                "role": m["role"] if isinstance(m, dict) else m.role,
                "content": m["content"] if isinstance(m, dict) else m.content,
            })

        while formatted and formatted[-1]["role"] == "assistant":
            formatted.pop()

        return formatted
    