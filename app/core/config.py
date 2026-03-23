"""配置管理模块。

负责从环境变量和 `.env` 文件中加载项目运行配置，
并在启动阶段对部分历史字段和派生字段做兼容补齐。
"""

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类。

    统一管理数据库、LLM、Embedding 等运行时配置。
    当前项目同时兼容历史字段命名和新的 provider 配置方式，
    这样可以降低脚本、服务层和旧文档之间的迁移成本。
    """

    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    APP_NAME: str = "optic-rag-demo"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/optic_rag"

    HF_TOKEN: str = ""
    OPENAI_API_KEY: str = ""

    # LLM provider 可选值：hf(openai-compatible) / openai / google
    LLM_PROVIDER: str = "hf"
    LLM_API_BASE: str = "https://router.huggingface.co/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL_NAME: str = Field(
        default="Qwen/Qwen2.5-7B-Instruct:together",
        validation_alias=AliasChoices("LLM_MODEL_NAME", "LLM_MODEL"),
    )

    # Embedding provider 可选值：hf(openai-compatible) / openai / google / mock
    EMBEDDING_PROVIDER: str = "hf"
    EMBEDDING_API_BASE: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL_NAME: str = Field(
        default="BAAI/bge-m3",
        validation_alias=AliasChoices("EMBEDDING_MODEL_NAME", "EMBEDDING_MODEL"),
    )

    GOOGLE_GENAI_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_GENAI_API_KEY", "GOOGLE_API_KEY"),
    )
    GOOGLE_MODEL_NAME: str = "gemini-2.5-flash"
    GOOGLE_EMBEDDING_MODEL_NAME: str = "gemini-embedding-001"

    # 历史字段保留给旧调用方使用，避免已有脚本直接失效。
    LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct:together"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug(cls, value):
        """把多种常见的环境变量写法归一化为布尔值。

        这样 `.env` 中使用 `debug/dev/prod/on/off` 等风格时，
        不会因为严格布尔解析而阻塞服务启动。
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "dev"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return value

    @model_validator(mode="after")
    def apply_fallbacks(self) -> "Settings":
        """加载完成后补齐派生配置和历史别名字段。

        这里集中处理默认回退逻辑，避免各个 service 自己重复判断：
        1. LLM 与 Embedding 缺省时复用已有 API Key
        2. Embedding 未显式指定 base_url 时复用 LLM 的 base_url
        3. 历史字段 `LLM_MODEL` / `EMBEDDING_MODEL` 与新字段保持同步
        """
        if not self.LLM_API_KEY:
            self.LLM_API_KEY = self.OPENAI_API_KEY or self.HF_TOKEN

        if not self.EMBEDDING_API_BASE:
            self.EMBEDDING_API_BASE = self.LLM_API_BASE

        if not self.EMBEDDING_API_KEY:
            self.EMBEDDING_API_KEY = self.OPENAI_API_KEY or self.HF_TOKEN

        if self.LLM_MODEL == "Qwen/Qwen2.5-7B-Instruct:together":
            self.LLM_MODEL = self.LLM_MODEL_NAME
        if self.EMBEDDING_MODEL == "BAAI/bge-m3":
            self.EMBEDDING_MODEL = self.EMBEDDING_MODEL_NAME

        return self


settings = Settings()
