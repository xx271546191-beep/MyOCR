from typing import List, Dict, Any


def build_qa_prompt(query: str, context_text: str) -> str:
    prompt = f"""你是一个光缆路由图信息提取助手。请根据以下上下文内容回答用户的问题。

要求：
1. 只允许基于提供的上下文内容回答问题
2. 如果上下文中没有相关信息，请明确说明"根据当前检索结果，未找到相关信息"
3. 尽量返回引用的 chunk_id

上下文内容：
{context_text}

用户问题：{query}

请给出回答："""
    return prompt


def build_extraction_prompt(context_text: str, schema_json: str) -> str:
    prompt = f"""你是一个光缆路由图信息提取助手。请根据以下上下文内容提取结构化信息。

上下文内容：
{context_text}

期望的输出格式（JSON Schema）：
{schema_json}

请按照上述格式提取信息，如果某个字段无法提取，请使用 null 或空值。
"""
    return prompt
