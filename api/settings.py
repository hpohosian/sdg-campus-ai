from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MISTRAL_API_KEY: str
    MISTRAL_MODEL: str = "mistral-medium-latest"

    MOODLE_SECRET: str

    # Requests per user and minute (0 = no limit). "LLM" = everything that
    # makes the language model answer (send, stream, edit, regenerate).
    RATE_LIMIT_PER_MIN: int = 120
    RATE_LIMIT_LLM_PER_MIN: int = 12

    # Data retention: chats whose last activity is older than this many days are
    # deleted by the daily cleanup (POST /privacy/maintenance, started by the
    # Moodle cron task). 0 = keep everything (retention OFF). The value is a
    # data-protection decision, not a technical one.
    CHAT_RETENTION_DAYS: int = 0

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    # Moodle's database (MariaDB). READ ONLY: course texts, PDFs, enrolments.
    # Goes away once the backend is decoupled from Moodle.
    DATABASE_URL: str

    # OUR database for chat data (PostgreSQL), e.g.
    # postgresql+psycopg://user:password@127.0.0.1:5433/sdgchat
    CHAT_DATABASE_URL: str
    
    MOODLEDATA_PATH: str = "D:\\Moodle\\MoodleWindowsInstaller-latest-500\\server\\moodledata"

    # Where chat-attached images are written to disk. Empty string (default)
    # means "<MOODLEDATA_PATH>/local_ai_system/chat_images" — override in
    # .env if you want them stored somewhere else (e.g. a separate volume).
    CHAT_IMAGES_DIR: str = ""

    # Used to build clickable course links in chatbot answers, e.g.
    # f"{MOODLE_BASE_URL}/course/view.php?id={course_id}"
    # Change this in .env for staging/production (no trailing slash).
    MOODLE_BASE_URL: str = "http://127.0.0.1"
    
    INTERNAL_API_KEY: str
    
    EMBEDDING_MODEL: str = "paraphrase-multilingual-mpnet-base-v2"
    HF_HOME: str = "D:\\hiwi\\huggingface_cache"
    HF_HUB_DISABLE_XET: str = "1"
    
    MISTRAL_VISION_MODEL: str = "mistral-medium-latest"

    # Model for translating chats when the user switches the language.
    # Empty = MISTRAL_MODEL. A smaller model (e.g. "mistral-small-latest")
    # writes tokens much faster; compare with eval/bench_translation.py.
    TRANSLATION_MODEL: str = ""

    # Model for the automatic chat title. Empty = MISTRAL_MODEL.
    TITLE_MODEL: str = ""

    # Model that turns an attached image into search keywords before the
    # course-material search (must understand images). Empty =
    # MISTRAL_VISION_MODEL. A fast model here saves ~1-3 s per image question.
    IMAGE_KEYWORDS_MODEL: str = ""

    # Which LLM API to use (llm/factory.py):
    #   "mistral"   - Mistral API with MISTRAL_API_KEY
    #   "kiconnect" - KI:connect.nrw / RWTHgpt (OpenAI-compatible) with
    #                 KICONNECT_API_KEY; model ids then come from KI:connect,
    #                 e.g. MISTRAL_MODEL=mistral-small-4-119b-2603
    LLM_PROVIDER: str = "mistral"
    KICONNECT_API_KEY: str = ""
    KICONNECT_BASE_URL: str = "https://chat.kiconnect.nrw/api/v1"

    # Client-side throttle: at most this many Mistral requests per second
    # PER MODEL from this process; extra requests wait in a queue instead of
    # getting HTTP 429. 0 = off. For the free plan (1 request/s on most
    # models) set 1. Leave 0 with a paid key that has higher limits.
    MISTRAL_MAX_RPS: float = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()
