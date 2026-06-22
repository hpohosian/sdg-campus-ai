from chatbot.prompts import RAG_SYSTEM_PROMPT, RAG_CONTEXT_TEMPLATE, NO_CONTEXT_PROMPT
from llm.base import BaseLLM
from rag.retriever import Retriever


class AIService:
    def __init__(self, llm: BaseLLM, retriever: Retriever = None):
        self.llm = llm
        self.retriever = retriever

    async def generate_response(self, messages, collection_name: str = None):
        # 1. Get last user message for retrieval
        user_query = self._get_last_user_message(messages)

        # 2. Format messages
        formatted = self._format(messages)

        # 3. Build system prompt (with or without RAG context)
        system_prompt = await self._build_system_prompt(user_query, collection_name)

        formatted.insert(0, {
            "role": "system",
            "content": system_prompt,
        })

        # 4. Call model
        return await self.llm.chat(formatted)

    async def stream_response(self, messages, collection_name: str = None):
        user_query = self._get_last_user_message(messages)

        formatted = self._format(messages)

        system_prompt = await self._build_system_prompt(user_query, collection_name)

        formatted.insert(0, {
            "role": "system",
            "content": system_prompt,
        })

        async for token in self.llm.stream(formatted):
            yield token

    async def _build_system_prompt(self, query: str, collection_name: str = None) -> str:
        """
        If retriever is available and collection exists — use RAG prompt with context.
        Otherwise — fall back to plain prompt.
        """
        if not self.retriever or not collection_name or not query:
            return NO_CONTEXT_PROMPT

        context = self.retriever.retrieve_as_context(
            query=query,
            collection_name=collection_name,
            n_results=3,
        )

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
    