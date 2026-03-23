"""RAG 场景使用的 Prompt 模板。"""


def build_qa_prompt(query: str, context_text: str) -> str:
    """构建基于检索上下文的问答 Prompt。"""
    prompt = f"""你是一个光缆路由图信息提取助手。请根据以下上下文内容回答用户的问题。

要求：
1. 只允许基于提供的上下文内容回答问题，不要编造信息。
2. 如果上下文中没有相关信息，请明确说明“根据当前检索结果，未找到相关信息”。
3. 回答时必须引用来源，格式如：[chunk_id: xxx]
4. 如果信息不完整或不确定，请明确指出。
5. 在回答末尾给出答案的置信度（0-1 之间）。

上下文内容：
{context_text}

用户问题：{query}

请给出回答（包括答案、依据引用和置信度）："""
    return prompt


def build_extraction_prompt(context_text: str, schema_json: str) -> str:
    """构建结构化抽取 Prompt。"""
    prompt = f"""你是一个光缆路由图信息提取助手。请根据以下上下文内容提取结构化信息。

上下文内容：
{context_text}

期望的输出格式（JSON Schema）：
{schema_json}

请按照上述格式提取信息，如果某个字段无法提取，请使用 null 或空值。
"""
    return prompt
