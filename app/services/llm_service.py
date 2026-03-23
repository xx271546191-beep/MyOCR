"""LLM 调用服务模块

负责封装大语言模型 (LLM) 的调用逻辑
支持多种 LLM 提供商 (HuggingFace, Google GenAI)
为 QA 问答、结构化抽取等任务提供文本生成能力
"""

from openai import OpenAI
from app.core.config import settings
from typing import List, Optional


class LLMService:
    """LLM 调用服务类
    
    负责封装大语言模型的调用，支持多种提供商
    提供文本生成、多模态理解等能力
    
    Attributes:
        model_name: 当前使用的 LLM 模型名称
        _client: OpenAI 兼容客户端 (懒加载)
        _google_client: Google GenAI 客户端 (懒加载)
    """
    
    def __init__(self):
        """初始化 LLM 服务
        
        设置默认模型名称，客户端实例采用懒加载模式
        """
        self.model_name = settings.LLM_MODEL_NAME

    @property
    def client(self):
        """获取 LLM 客户端实例
        
        采用懒加载模式，首次访问时创建实例
        根据配置自动选择 OpenAI 兼容客户端或 Google GenAI 客户端
        
        Returns:
            OpenAI or genai.Client: LLM 客户端实例
            
        Raises:
            RuntimeError: 使用 Google provider 但未配置 API KEY
        """
        # 确保属性存在 (避免首次访问错误)
        if not hasattr(self, "_client"):
            self._client = None
        if not hasattr(self, "_google_client"):
            self._google_client = None

        # 根据配置选择提供商
        provider = (settings.LLM_PROVIDER or "hf").lower()
        if provider == "google":
            if self._google_client is None:
                if not settings.GOOGLE_GENAI_API_KEY:
                    raise RuntimeError("GOOGLE_GENAI_API_KEY is required when LLM_PROVIDER=google")
                from google import genai  # type: ignore
                self._google_client = genai.Client(api_key=settings.GOOGLE_GENAI_API_KEY)
            return self._google_client

        # 使用 OpenAI 兼容客户端 (HuggingFace, Together 等)
        if self._client is None:
            self._client = OpenAI(
                base_url=settings.LLM_API_BASE,
                api_key=settings.LLM_API_KEY
            )
        return self._client

    def generate_answer(
        self,
        prompt: str,
        images: Optional[List[str]] = None
    ) -> str:
        """使用 LLM 生成回答
        
        支持纯文本和多模态 (文本 + 图片) 输入
        根据配置自动选择 Google 或 OpenAI 兼容接口
        
        Args:
            prompt: 提示词/问题
            images: 图片 URL 列表 (可选，用于多模态理解)
            
        Returns:
            str: LLM 生成的回答文本
            
        Raises:
            NotImplementedError: Google provider 不支持图片输入
        """
        provider = (settings.LLM_PROVIDER or "hf").lower()
        if provider == "google":
            # Google GenAI 实现 (当前仅支持文本)
            # 注意：Google provider 暂不支持图片输入
            if images:
                raise NotImplementedError("images are not supported for Google provider in this demo")
            client = self.client
            response = client.models.generate_content(
                model=settings.GOOGLE_MODEL_NAME,
                contents=prompt,
            )
            return (getattr(response, "text", None) or "").strip()

        # OpenAI 兼容实现 (支持多模态)
        messages = [{"role": "user", "content": prompt}]

        # 如果有图片，构建多模态消息
        if images:
            image_contents = [{"type": "image_url", "image_url": {"url": img}} for img in images]
            messages[0]["content"] = [
                {"type": "text", "text": prompt},
                *image_contents
            ]

        # 调用 LLM 生成回答
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages
        )
        return response.choices[0].message.content


# 全局单例，供整个应用使用
llm_service = LLMService()


def generate_answer(prompt: str, images: Optional[List[str]] = None) -> str:
    """便捷函数：使用 LLM 生成回答
    
    Args:
        prompt: 提示词/问题
        images: 图片 URL 列表 (可选)
        
    Returns:
        str: LLM 生成的回答文本
    """
    return llm_service.generate_answer(prompt, images)


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    images: Optional[List[str]] = None,
) -> str:
    """统一的 LLM 调用入口（供 extraction / retrieval / graph 使用）。

    注意：
    - 通过 system_prompt + user_prompt 组合，尽量保留“系统约束”能力
    - 当 provider=google 时当前 demo 仅支持文本（不支持 images）
    """
    provider = (settings.LLM_PROVIDER or "hf").lower()
    effective_model = model or llm_service.model_name

    # Google GenAI provider
    if provider == "google":
        if images:
            raise NotImplementedError("images are not supported for Google provider in this demo")
        client = llm_service.client
        contents = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
        response = client.models.generate_content(
            model=model or settings.GOOGLE_MODEL_NAME,
            contents=contents,
        )
        return (getattr(response, "text", None) or "").strip()

    # OpenAI 兼容 provider
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if images:
        image_contents = [{"type": "image_url", "image_url": {"url": img}} for img in images]
        user_content: object = [{"type": "text", "text": user_prompt}, *image_contents]
    else:
        user_content = user_prompt

    messages.append({"role": "user", "content": user_content})

    response = llm_service.client.chat.completions.create(
        model=effective_model,
        messages=messages,
    )
    return response.choices[0].message.content
