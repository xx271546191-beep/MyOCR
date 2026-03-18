from openai import OpenAI
from app.core.config import settings
from typing import List, Optional


class LLMService:
    def __init__(self):
        self._client = None
        self.model_name = settings.LLM_MODEL

    @property
    def client(self):
        if self._client is None:
            self._client = OpenAI(
                base_url="https://router.huggingface.co/v1",
                api_key=settings.HF_TOKEN
            )
        return self._client

    def generate_answer(
        self,
        prompt: str,
        images: Optional[List[str]] = None
    ) -> str:
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
