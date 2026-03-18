from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    APP_NAME: str = "optic-rag-demo"
    DEBUG: bool = True
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./optic_rag.db"
    )
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")

    # Unified naming (preferred)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "hf")  # hf | google
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://router.huggingface.co/v1")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct:together"))

    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "hf")
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"))

    # Google Gemini (optional)
    GOOGLE_GENAI_API_KEY: str = os.getenv("GOOGLE_GENAI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    GOOGLE_MODEL_NAME: str = os.getenv("GOOGLE_MODEL_NAME", "gemini-2.5-flash")
    GOOGLE_EMBEDDING_MODEL_NAME: str = os.getenv("GOOGLE_EMBEDDING_MODEL_NAME", "gemini-embedding-001")

    # Backward compatible fields (avoid using in code)
    LLM_MODEL: str = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct:together")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
