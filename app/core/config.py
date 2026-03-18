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
    EMBEDDING_MODEL_NAME: str = "qwen3-vl-embedding"
    LLM_MODEL_NAME: str = "qwen-vl"
    EMBEDDING_API_BASE: str = "http://localhost:8001/v1"
    LLM_API_BASE: str = "http://localhost:8002/v1"
    EMBEDDING_API_KEY: str = "demo"
    LLM_API_KEY: str = "demo"
    HF_TOKEN: str = ""
    LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct:together"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
