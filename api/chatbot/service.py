from llm.mistral import MistralLLM
from chatbot.prompts import SYSTEM_PROMPT

class ChatService():
    def __init__(self):
        self.llm = MistralLLM()
        
    def generate_response(self, user_message: str) -> str:
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user_message
            }
        ]

        response = self.llm.generate(messages)

        return response