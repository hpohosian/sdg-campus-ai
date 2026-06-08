from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MISTRAL_API_KEY: str
    MISTRAL_MODEL: str = "mistral-medium"

    MOODLE_SECRET: str

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    DATABASE_URL: str
    
    EMBEDDING_MODEL: str = "paraphrase-multilingual-mpnet-base-v2"
    HF_HOME: str = "D:\\hiwi\\huggingface_cache"
    HF_HUB_DISABLE_XET: str = "1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()
