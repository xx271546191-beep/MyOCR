from openai import OpenAI
from app.core.config import settings
from typing import List, Optional


class LLMService:
    def __init__(self):
        self.model_name = settings.LLM_MODEL_NAME

    @property
    def client(self):
        # Keep a client per provider to avoid repeated init.
        if not hasattr(self, "_client"):
            self._client = None
        if not hasattr(self, "_google_client"):
            self._google_client = None

        provider = (settings.LLM_PROVIDER or "hf").lower()
        if provider == "google":
            if self._google_client is None:
                if not settings.GOOGLE_GENAI_API_KEY:
                    raise RuntimeError("GOOGLE_GENAI_API_KEY is required when LLM_PROVIDER=google")
                from google import genai  # type: ignore
                self._google_client = genai.Client(api_key=settings.GOOGLE_GENAI_API_KEY)
            return self._google_client

        if self._client is None:
            self._client = OpenAI(
                base_url=settings.LLM_API_BASE,
                api_key=settings.HF_TOKEN
            )
        return self._client

    def generate_answer(
        self,
        prompt: str,
        images: Optional[List[str]] = None
    ) -> str:
        provider = (settings.LLM_PROVIDER or "hf").lower()
        if provider == "google":
            # Minimal text-only implementation for demo stability.
            if images:
                raise NotImplementedError("images are not supported for Google provider in this demo")
            client = self.client
            response = client.models.generate_content(
                model=settings.GOOGLE_MODEL_NAME,
                contents=prompt,
            )
            return (getattr(response, "text", None) or "").strip()

        messages = [{"role": "user", "content": prompt}]

        if images:
            image_contents = [{"type": "image_url", "image_url": {"url": img}} for img in images]
            messages[0]["content"] = [
                {"type": "text", "text": prompt},
                *image_contents
            ]

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages
        )
        return response.choices[0].message.content


llm_service = LLMService()


def generate_answer(prompt: str, images: Optional[List[str]] = None) -> str:
    return llm_service.generate_answer(prompt, images)
