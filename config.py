import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
    MODEL_NAME = os.getenv("MODEL_NAME", "mistral-large-latest")
    