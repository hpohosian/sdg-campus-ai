from chatbot.prompts import RAG_SYSTEM_PROMPT, RAG_CONTEXT_TEMPLATE, NO_CONTEXT_PROMPT
from llm.base import BaseLLM
from rag.retriever import Retriever


_TITLE_SYSTEM_PROMPT = (
    "Generate a short, descriptive title (3-6 words) summarizing this chat exchange. "
    "Write the title in the same language as the conversation. "
    "Return ONLY the title text — no quotes, no trailing punctuation, no explanations."
)


class AIService:
    def __init__(self, llm: BaseLLM, retriever: Retriever = None):
        self.llm = llm
        self.retriever = retriever
        
    async def generate_title(self, user_message: str, assistant_message: str) -> str:
        messages = [
            {"role": "system", "content": _TITLE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Student: {user_message}\nAssistant: {assistant_message}"},
        ]
        title = await self.llm.chat(messages)
        return title.strip().strip('"').strip("'")[:255]

    async def generate_response(
        self,
        messages,
        collection_name: str = None,
        course_ids: list[int] = None,
        course_link: str = None,
        course_links: dict[int, str] = None,
    ):
        retrieval_query = self._build_retrieval_query(messages)
        formatted = self._format(messages)
        system_prompt = await self._build_system_prompt(
            retrieval_query, collection_name, course_ids, course_link, course_links
        )

        formatted.insert(0, {
            "role": "system",
            "content": system_prompt,
        })

        return await self.llm.chat(formatted)

    async def stream_response(
        self,
        messages,
        collection_name: str = None,
        course_ids: list[int] = None,
        course_link: str = None,
        course_links: dict[int, str] = None,
    ):
        retrieval_query = self._build_retrieval_query(messages)
        formatted = self._format(messages)
        system_prompt = await self._build_system_prompt(
            retrieval_query, collection_name, course_ids, course_link, course_links
        )

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
        course_link: str = None,
        course_links: dict[int, str] = None,
    ) -> str:
        """
        Priority:
        1. If a specific course is selected (collection_name) — search only that course.
        2. Otherwise, if the user has enrolled courses (course_ids) — search across all of them.
        3. Otherwise — plain LLM, no RAG context.

        course_link / course_links: pre-built markdown link(s) for the
        course(s) in scope (see chatbot/course_links.py). These are
        purely cosmetic for citation — retrieval itself is unaffected
        whether they're passed or not.
        """
        if not self.retriever or not query:
            return NO_CONTEXT_PROMPT

        if collection_name:
            context = self.retriever.retrieve_as_context(
                query=query,
                collection_name=collection_name,
                n_results=8,
                course_link=course_link,
            )
        elif course_ids:
            context = self.retriever.retrieve_as_context_global(
                query=query,
                course_ids=course_ids,
                n_results=8,
                course_links=course_links,
            )
        else:
            context = ""

        if not context:
            return NO_CONTEXT_PROMPT

        return RAG_SYSTEM_PROMPT + RAG_CONTEXT_TEMPLATE.format(context=context)

    def _get_last_user_message(self, messages) -> str:
        """Extract the last user message text."""
        for msg in reversed(messages):
            role = msg["role"] if isinstance(msg, dict) else msg.role
            content = msg["content"] if isinstance(msg, dict) else msg.content
            if role == "user":
                return content
        return ""

    def _build_retrieval_query(self, messages, max_user_messages: int = 2) -> str:
        """
        Builds the text used for vector search.

        Using ONLY the very last user message breaks on short follow-up
        questions like "which file is this from?" or "can you explain
        that more?" — on their own, such messages carry almost no topical
        signal, so the embedding search drifts to unrelated chunks even
        though the conversation is clearly still about the previous topic.

        Fix: concatenate the last `max_user_messages` user messages (most
        recent last, since some embedding models weight later tokens
        more). This keeps retrieval anchored to the actual topic being
        discussed without needing a separate LLM call to rewrite the
        query.

        NOTE: this is a heuristic, not a full query-rewrite step. For
        longer/more tangled conversations, consider replacing this with
        an explicit "condense the question given chat history" LLM call
        instead — more robust, but adds latency and an extra LLM call
        per turn.
        """
        user_messages = []
        for msg in messages:
            role = msg["role"] if isinstance(msg, dict) else msg.role
            content = msg["content"] if isinstance(msg, dict) else msg.content
            if role == "user" and content:
                user_messages.append(content)

        recent = user_messages[-max_user_messages:]
        return "\n".join(recent)

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
    