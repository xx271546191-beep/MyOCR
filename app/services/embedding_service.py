"""向量化服务模块。

负责统一封装不同 provider 的文本向量化调用，
对外暴露稳定的 `embed_text` / `embed_texts` 接口，
避免上层服务感知不同 SDK 的差异。
"""

import hashlib
from typing import List

from huggingface_hub import InferenceClient
from openai import OpenAI

from app.core.config import settings


EMBEDDING_DIMENSIONS = {
    "BAAI/bge-m3": 1024,
    "BAAI/bge-base-en-v1.5": 768,
    "BAAI/bge-small-en-v1.5": 384,
    "intfloat/e5-base-v2": 768,
    "intfloat/e5-small-v2": 384,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "gemini-embedding-001": 768,
}

OPENAI_COMPATIBLE_PROVIDERS = {"openai"}


class EmbeddingService:
    """向量化服务类。

    当前支持三类 provider：
    1. Hugging Face feature extraction
    2. OpenAI-compatible embeddings
    3. Google GenAI embeddings

    通过统一入口屏蔽 provider 差异，便于 retrieval、ingest 等模块复用。
    """

    def __init__(self) -> None:
        """初始化向量化服务。

        客户端采用懒加载方式创建，避免应用启动时立刻校验全部外部依赖，
        这样只有真正用到某个 provider 时才要求对应密钥完整。
        """
        self._hf_client = None
        self._openai_client = None
        self._google_client = None
        self.model_name = settings.EMBEDDING_MODEL_NAME

    @property
    def hf_client(self) -> InferenceClient:
        """获取 Hugging Face 向量化客户端。"""
        if self._hf_client is None:
            api_key = settings.HF_TOKEN or settings.EMBEDDING_API_KEY
            if not api_key:
                raise RuntimeError(
                    "HF_TOKEN or EMBEDDING_API_KEY is required "
                    "when EMBEDDING_PROVIDER=hf"
                )
            self._hf_client = InferenceClient(
                provider="hf-inference",
                api_key=api_key,
            )
        return self._hf_client

    @property
    def openai_client(self) -> OpenAI:
        """获取 OpenAI-compatible 向量化客户端。"""
        if self._openai_client is None:
            api_key = settings.EMBEDDING_API_KEY or settings.OPENAI_API_KEY
            if not api_key:
                raise RuntimeError(
                    "EMBEDDING_API_KEY or OPENAI_API_KEY is required "
                    "when EMBEDDING_PROVIDER=openai"
                )

            self._openai_client = OpenAI(
                base_url=settings.EMBEDDING_API_BASE,
                api_key=api_key,
            )
        return self._openai_client

    @property
    def google_client(self):
        """获取 Google GenAI 向量化客户端。"""
        if self._google_client is None:
            if not settings.GOOGLE_GENAI_API_KEY:
                raise RuntimeError(
                    "GOOGLE_GENAI_API_KEY is required when EMBEDDING_PROVIDER=google"
                )
            from google import genai

            self._google_client = genai.Client(api_key=settings.GOOGLE_GENAI_API_KEY)
        return self._google_client

    def get_embedding_dimension(self) -> int:
        """返回当前模型理论上的向量维度。"""
        provider = (settings.EMBEDDING_PROVIDER or "hf").lower()
        if provider == "google":
            return EMBEDDING_DIMENSIONS.get(settings.GOOGLE_EMBEDDING_MODEL_NAME, 768)
        return EMBEDDING_DIMENSIONS.get(self.model_name, 1024)

    def _coerce_vector(self, value) -> List[float]:
        """把不同 SDK 返回值统一转换为 float 向量列表。"""
        if hasattr(value, "tolist"):
            value = value.tolist()

        # 某些 provider 会返回二维数组，这里只取单条文本对应的向量。
        if isinstance(value, list) and value and isinstance(value[0], list):
            value = value[0]

        if not isinstance(value, list) or not value:
            raise RuntimeError("embedding provider returned empty vector")
        return [float(x) for x in value]

    def _embed_text_hf(self, text: str) -> List[float]:
        """使用 Hugging Face provider 生成单条文本向量。"""
        result = self.hf_client.feature_extraction(
            text,
            model=self.model_name,
        )
        return self._coerce_vector(result)

    def _embed_text_openai(self, text: str) -> List[float]:
        """使用 OpenAI-compatible provider 生成单条文本向量。"""
        response = self.openai_client.embeddings.create(
            model=self.model_name,
            input=text,
        )
        data = getattr(response, "data", None) or []
        if not data or not getattr(data[0], "embedding", None):
            raise RuntimeError("openai-compatible embedding provider returned empty vector")
        return self._coerce_vector(data[0].embedding)

    def _embed_text_google(self, text: str) -> List[float]:
        """使用 Google provider 生成单条文本向量。"""
        response = self.google_client.models.embed_content(
            model=settings.GOOGLE_EMBEDDING_MODEL_NAME,
            contents=text,
        )
        embeddings = getattr(response, "embeddings", None) or []
        if not embeddings:
            raise RuntimeError("google embedding provider returned empty embeddings")

        emb0 = embeddings[0]
        values = getattr(getattr(emb0, "embedding", None), "values", None)
        if values is None:
            try:
                values = emb0["embedding"]["values"]
            except Exception:
                values = None

        if not isinstance(values, list) or not values:
            raise RuntimeError("google embedding provider returned empty vector")
        return [float(x) for x in values]

    def _embed_text_mock(self, text: str) -> List[float]:
        """使用本地 mock provider 生成稳定向量。

        该实现不依赖外部网络，主要用于测试和本地可复现验证。
        """
        dimension = self.get_embedding_dimension()
        values: list[float] = []
        counter = 0
        while len(values) < dimension:
            payload = f"{self.model_name}|{text}|{counter}".encode("utf-8")
            digest = hashlib.sha256(payload).digest()
            for index in range(0, len(digest), 4):
                chunk = digest[index : index + 4]
                if len(chunk) < 4:
                    continue
                raw = int.from_bytes(chunk, "big", signed=False)
                values.append((raw / 4294967295.0) * 2.0 - 1.0)
                if len(values) >= dimension:
                    break
            counter += 1
        return values

    def embed_text(self, text: str) -> List[float]:
        """为单条文本生成向量。

        这里统一做输入校验，避免下游 provider 在空字符串场景返回不一致错误。
        """
        if not text or not text.strip():
            raise ValueError("text must be non-empty")

        provider = (settings.EMBEDDING_PROVIDER or "hf").lower()
        if provider == "google":
            return self._embed_text_google(text)
        if provider == "mock":
            return self._embed_text_mock(text)
        if provider == "hf":
            return self._embed_text_hf(text)
        if provider in OPENAI_COMPATIBLE_PROVIDERS:
            return self._embed_text_openai(text)
        raise ValueError(f"unsupported embedding provider: {provider}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """为多条文本批量生成向量。"""
        if texts is None:
            raise ValueError("texts must not be None")
        if not texts:
            return []
        if any(not text or not text.strip() for text in texts):
            raise ValueError("all texts must be non-empty")

        provider = (settings.EMBEDDING_PROVIDER or "hf").lower()
        if provider == "google":
            return [self._embed_text_google(text) for text in texts]
        if provider == "mock":
            return [self._embed_text_mock(text) for text in texts]
        if provider == "hf":
            return [self._embed_text_hf(text) for text in texts]

        if provider in OPENAI_COMPATIBLE_PROVIDERS:
            response = self.openai_client.embeddings.create(
                model=self.model_name,
                input=texts,
            )
            data = getattr(response, "data", None) or []
            if len(data) != len(texts):
                raise RuntimeError("openai-compatible embedding provider returned incomplete batch")

            vectors = []
            for item in data:
                vector = getattr(item, "embedding", None)
                if not isinstance(vector, list) or not vector:
                    raise RuntimeError("openai-compatible embedding provider returned empty vector")
                vectors.append([float(x) for x in vector])
            return vectors

        raise ValueError(f"unsupported embedding provider: {provider}")


embedding_service = EmbeddingService()


def embed_text(text: str) -> List[float]:
    """便捷函数：生成单条文本向量。"""
    return embedding_service.embed_text(text)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """便捷函数：批量生成文本向量。"""
    return embedding_service.embed_texts(texts)


def get_embedding_dimension() -> int:
    """便捷函数：获取当前模型维度。"""
    return embedding_service.get_embedding_dimension()
