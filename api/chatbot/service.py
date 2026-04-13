from chatbot.prompts import SYSTEM_PROMPT

from llm.mistral import MistralLLM
from chatbot.session_repository import SessionRepository
from chatbot.schemas import ChatRequest, ChatResponse


class ChatService():
    def __init__(self, llm: MistralLLM, session_repo: SessionRepository):
        self.llm = llm
        self.session_repo = session_repo
        
    def _build_messages(self, history, new_message):
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

        for message in history:
            messages.append({
                "role": message.role,
                "content": message.content
            })

        messages.append({
            "role": "user",
            "content": new_message
        })

        return messages
        
    async def handle_message(self, request: ChatRequest) -> ChatResponse:
        # 1. Load or create session
        session = await self.session_repo.get_or_create(request.session_id, request.user_id)
        
        # 2. Load history
        history = await self.session_repo.get_messages(session.id)
        
        # 3. Build message list for LLM (system + history + new message)
        messages = self._build_messages(history, request.message)
        
        # 4. Call LLM
        response_text = await self.llm.chat(messages)
        
        # 5. Save both messages
        await self.session_repo.save_message(session.id, "user", request.message)
        await self.session_repo.save_message(session.id, "assistant", response_text)
        
        return ChatResponse(session_id=session.id, message=response_text)
    