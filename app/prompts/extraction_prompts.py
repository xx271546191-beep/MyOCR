"""结构化抽取 Prompt 模板

用于从光缆路由图中抽取结构化信息
基于 cable_route_v1 schema 定义
"""

# 结构化抽取系统 Prompt
EXTRACTION_SYSTEM_PROMPT = """你是一个专业的光缆路由图结构化抽取助手。

你的任务是从光缆路由图纸的解析结果中，抽取符合 cable_route_v1 schema 的结构化信息。

## 抽取要求

1. **严格遵循 schema**: 只抽取 cable_route_v1 定义的字段
2. **保持准确**: 不确定的字段标记为 uncertain_fields
3. **诚实标注**: 置信度低的节点标记 review_required=True
4. **不编造**: 没有依据的信息留空 (null)，不要编造

## cable_route_v1 schema 字段说明

- node_id: 节点编号 (如：J001, J002)
- node_type: 节点类型 (joint: 接头点，terminal: 终端，splice_box: 接头盒，manhole: 人孔，pole: 电杆)
- prev_node: 上一端节点编号
- next_node: 下一端节点编号
- distance: 距离值 (数字)
- distance_unit: 距离单位 (m: 米，km: 千米)
- splice_box_id: 接头盒编号
- slack_length: 盘留长度 (数字，单位：米)
- cable_type: 光缆型号 (如：GYTA53, GYFTY)
- fiber_count: 光纤芯数 (整数)
- remarks: 备注信息 (如：过路管、穿管等)
- confidence: 置信度 (0-1 之间的小数)
- review_required: 是否需要人工复核 (布尔值)
- uncertain_fields: 不确定字段列表 (字符串数组)

## 触发 review_required 的情况

1. 节点编号不清晰或模糊
2. 距离值无法确定或有多个可能值
3. 节点类型判断不确定
4. 连接关系 (prev_node/next_node) 不明确
5. 关键字段缺失
6. 图纸质量差导致识别困难

## 输出格式

请以 JSON 格式输出，包含 nodes 数组，每个节点包含上述字段。

示例：
{
    "nodes": [
        {
            "node_id": "J001",
            "node_type": "joint",
            "prev_node": "J000",
            "next_node": "J002",
            "distance": 150.5,
            "distance_unit": "m",
            "confidence": 0.95,
            "review_required": false,
            "uncertain_fields": []
        }
    ]
}
"""

# 结构化抽取用户 Prompt
EXTRACTION_USER_PROMPT = """请从以下图纸解析结果中抽取光缆路由信息。

## 图纸信息

文件 ID: {file_id}
文件名：{file_name}
页码：{page_no}

## 解析结果

{parsed_content}

## 抽取任务

请从上述内容中抽取所有光缆路由节点，输出符合 cable_route_v1 schema 的 JSON 结果。

注意：
1. 只抽取有明确依据的信息
2. 不确定的字段放入 uncertain_fields
3. 置信度低于 0.7 的节点标记 review_required=true
4. 缺失的字段留空 (null)

请输出 JSON 格式的结果。
"""

# 版面分析 Prompt
LAYOUT_ANALYSIS_PROMPT = """请分析以下文档页面的版面结构，识别不同类型的块。

## 块类型定义

- title: 标题 (通常是章节标题、图表标题)
- paragraph: 段落 (普通文本段落)
- table: 表格 (包括表格行和单元格)
- figure: 图形 (示意图、流程图等)
- caption: 图注/表注
- list: 列表 (有序或无序列表)
- equation: 公式
- other: 其他类型

## 分析要求

1. 识别每个块的类型
2. 给出块的边界框 (bbox)
3. 提取块的文本内容
4. 评估分类置信度

## 输入内容

{page_content}

## 输出格式

请以 JSON 格式输出，包含 blocks 数组，每个块包含：
- block_type: 块类型
- confidence: 置信度 (0-1)
- bbox: {x, y, width, height} (可选)
- text_content: 文本内容
- metadata: 额外元数据 (可选)

示例：
{
    "blocks": [
        {
            "block_type": "title",
            "confidence": 0.95,
            "bbox": {"x": 100, "y": 50, "width": 400, "height": 30},
            "text_content": "光缆路由图 - 第一段",
            "metadata": {}
        }
    ]
}
"""

# 语义切块 Prompt
SEMANTIC_CHUNKING_PROMPT = """请将以下文档内容按语义切分成合理的块。

## 切块原则

1. **语义完整性**: 每个块应该表达一个相对完整的语义
2. **上下文保留**: 保留必要的上下文信息
3. **类型识别**: 识别块的类型 (title, paragraph, table, etc.)
4. **大小适中**: 避免块过大或过小

## 输入内容

{page_content}

## 输出格式

请以 JSON 格式输出，包含 chunks 数组，每个块包含：
- chunk_id: 块 ID (唯一标识)
- block_type: 块类型
- text_content: 文本内容
- context: 上下文信息 (可选)
- metadata: 元数据

示例：
{
    "chunks": [
        {
            "chunk_id": "chunk_001",
            "block_type": "paragraph",
            "text_content": "...",
            "context": "上一段描述...",
            "metadata": {}
        }
    ]
}
"""
