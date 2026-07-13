from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MISTRAL_API_KEY: str
    MISTRAL_MODEL: str = "mistral-medium"

    MOODLE_SECRET: str

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    DATABASE_URL: str
    
    MOODLEDATA_PATH: str = "D:\\Moodle\\MoodleWindowsInstaller-latest-500\\server\\moodledata"

    # Used to build clickable course links in chatbot answers, e.g.
    # f"{MOODLE_BASE_URL}/course/view.php?id={course_id}"
    # Change this in .env for staging/production (no trailing slash).
    MOODLE_BASE_URL: str = "http://127.0.0.1"
    
    INTERNAL_API_KEY: str
    
    EMBEDDING_MODEL: str = "paraphrase-multilingual-mpnet-base-v2"
    HF_HOME: str = "D:\\hiwi\\huggingface_cache"
    HF_HUB_DISABLE_XET: str = "1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()
