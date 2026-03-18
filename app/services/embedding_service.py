from app.core.config import settings
from typing import List
from huggingface_hub import InferenceClient


class EmbeddingService:
    def __init__(self):
        self._client = None
        self._google_client = None
        self.model_name = settings.EMBEDDING_MODEL_NAME

    @property
    def client(self):
        if self._client is None:
            # Use HuggingFace Inference API for embeddings.
            self._client = InferenceClient(token=settings.HF_TOKEN)
        return self._client

    @property
    def google_client(self):
        if self._google_client is None:
            if not settings.GOOGLE_GENAI_API_KEY:
                raise RuntimeError("GOOGLE_GENAI_API_KEY is required when EMBEDDING_PROVIDER=google")
            from google import genai  # type: ignore
            self._google_client = genai.Client(api_key=settings.GOOGLE_GENAI_API_KEY)
        return self._google_client

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("text must be non-empty")

        provider = (settings.EMBEDDING_PROVIDER or "hf").lower()
        if provider == "google":
            response = self.google_client.models.embed_content(
                model=settings.GOOGLE_EMBEDDING_MODEL_NAME,
                contents=text,
            )
            # response.embeddings[0].values
            embeddings = getattr(response, "embeddings", None) or []
            if not embeddings:
                raise RuntimeError("google embedding provider returned empty embeddings")
            emb0 = embeddings[0]
            values = getattr(getattr(emb0, "embedding", None), "values", None)
            if values is None:
                # Some versions may return dict-like structures
                try:
                    values = emb0["embedding"]["values"]  # type: ignore[index]
                except Exception:
                    values = None
            vec = values
        else:
            vec = self.client.feature_extraction(text, model=self.model_name)

        if not isinstance(vec, list) or not vec:
            raise RuntimeError("embedding provider returned empty vector")
        return [float(x) for x in vec]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if texts is None:
            raise ValueError("texts must not be None")
        return [self.embed_text(t) for t in texts]


embedding_service = EmbeddingService()


def embed_text(text: str) -> List[float]:
    return embedding_service.embed_text(text)


def embed_texts(texts: List[str]) -> List[List[float]]:
    return embedding_service.embed_texts(texts)
