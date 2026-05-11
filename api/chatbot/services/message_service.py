from chatbot.repositories.message_repository import MessageRepository
from chatbot.repositories.session_repository import SessionRepository

# Позже здесь будут:
# validation
# permissions
# pagination
# token limits
# LLM orchestration

class MessageService:
    def __init__(self, message_repo: MessageRepository, session_repo: SessionRepository):
        self.message_repo = message_repo
        self.session_repo = session_repo


    # =========================
    # GET SESSION MESSAGES
    # =========================
    async def get_session_messages(self, session_id: str):
        messages = self.message_repo.get_by_session(session_id)

        return messages
    
    
    # =========================
    # SAVE USER MESSAGE ONLY
    # =========================
    async def create_user_message(self, session_id: str, content: str):
        session = self.session_repo.get(session_id)

        if not session:
            raise ValueError("Session not found")

        return self.message_repo.create(
            session_id=session_id,
            role="user",
            content=content,
        )
        
    
    # =========================
    # SAVE ASSISTANT MESSAGE ONLY
    # =========================
    async def create_assistant_message(self, session_id: str, content: str, tokens_used: int | None = None):
        session = self.session_repo.get(session_id)
        
        if not session:
            raise ValueError("Session not found")
        
        return self.message_repo.create(
            session_id=session_id,
            role="assistant",
            content=content,
        )