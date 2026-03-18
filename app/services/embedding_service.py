from huggingface_hub import InferenceClient
from app.core.config import settings
from typing import List


class EmbeddingService:
    def __init__(self):
        self._client = None
        self.model_name = settings.EMBEDDING_MODEL

    @property
    def client(self):
        if self._client is None:
            self._client = InferenceClient(
                provider="hf-inference",
                api_key=settings.HF_TOKEN
            )
        return self._client

    def embed_text(self, text: str) -> List[float]:
        # 使用sentence_similarity获取embedding
        response = self.client.sentence_similarity(
            sentence=text,
            other_sentences=[text],
            model=self.model_name
        )
        return [response[0]] if response else [0.0] * 768

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            embedding = self.embed_text(text)
            embeddings.append(embedding)
        return embeddings


embedding_service = EmbeddingService()


def embed_text(text: str) -> List[float]:
    return embedding_service.embed_text(text)


def embed_texts(texts: List[str]) -> List[List[float]]:
    return embedding_service.embed_texts(texts)
