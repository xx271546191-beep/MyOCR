"""规则校核服务模块

负责对结构化抽取结果进行校核
检测字段冲突、缺失、异常
计算置信度
自动标记 review_required
识别不确定字段
"""

from typing import List, Dict, Any, Optional, Set
from app.schemas.extraction import CableRouteNode, ExtractionResponse
from app.db import models
from sqlalchemy.orm import Session


class RuleCheckService:
    """规则校核服务类
    
    负责校核结构化抽取结果的质量
    检测问题并标记需要人工复核的节点
    
    校核规则:
        1. 字段冲突检测 (如同一节点有多个距离值)
        2. 关键字段缺失检测
        3. 异常值检测 (如距离为负数)
        4. 逻辑关系校核 (如 prev_node 和 next_node 一致性)
        5. 置信度计算
    
    Attributes:
        confidence_threshold: 置信度阈值，低于此值标记 review_required
        required_fields: 必填字段列表
    """
    
    def __init__(
        self,
        confidence_threshold: float = 0.7,
        required_fields: Optional[List[str]] = None
    ):
        """初始化规则校核服务
        
        Args:
            confidence_threshold: 置信度阈值，默认 0.7
            required_fields: 必填字段列表，默认包含 node_id, node_type
        """
        self.confidence_threshold = confidence_threshold
        
        # 必填字段 (core fields)
        self.required_fields = required_fields or [
            "node_id",
            "node_type"
        ]
        
        # 距离相关字段
        self.distance_fields = ["distance", "slack_length"]
        
        # 连接关系字段
        self.relation_fields = ["prev_node", "next_node"]
    
    def check_nodes(
        self,
        nodes: List[CableRouteNode]
    ) -> List[CableRouteNode]:
        """校核节点列表
        
        对每个节点执行所有校核规则
        更新 confidence、review_required、uncertain_fields
        
        Args:
            nodes: 待校核的节点列表
            
        Returns:
            List[CableRouteNode]: 校核后的节点列表
        """
        checked_nodes = []
        
        for node in nodes:
            # 校核单个节点
            checked_node = self.check_single_node(node)
            checked_nodes.append(checked_node)
        
        # 执行跨节点校核 (检测节点间关系)
        self._cross_check_nodes(checked_nodes)
        
        return checked_nodes
    
    def check_single_node(
        self,
        node: CableRouteNode
    ) -> CableRouteNode:
        """校核单个节点
        
        执行所有校核规则
        
        Args:
            node: 待校核的节点
            
        Returns:
            CableRouteNode: 校核后的节点
        """
        uncertain_fields: List[str] = []
        confidence_deductions = 0.0  # 置信度扣减
        
        # Rule 1: 检查必填字段
        for field in self.required_fields:
            value = getattr(node, field)
            if value is None or value == "":
                uncertain_fields.append(field)
                confidence_deductions += 0.2
        
        # Rule 2: 检查字段冲突 (自相矛盾)
        conflicts = self._check_field_conflicts(node)
        if conflicts:
            uncertain_fields.extend(conflicts)
            confidence_deductions += 0.15 * len(conflicts)
        
        # Rule 3: 检查异常值
        anomalies = self._check_anomalies(node)
        if anomalies:
            uncertain_fields.extend(anomalies)
            confidence_deductions += 0.1 * len(anomalies)
        
        # Rule 4: 检查缺失字段
        missing = self._check_missing_fields(node)
        if missing:
            # 缺失字段不加入 uncertain_fields，但降低置信度
            confidence_deductions += 0.05 * len(missing)
        
        # 计算最终置信度
        final_confidence = max(0.0, node.confidence - confidence_deductions)
        
        # 判断是否需要 review
        needs_review = (
            final_confidence < self.confidence_threshold or
            len(uncertain_fields) > 0 or
            any(getattr(node, field) is None for field in self.required_fields)
        )
        
        # 更新节点
        node.confidence = final_confidence
        node.review_required = needs_review
        node.uncertain_fields = uncertain_fields
        
        return node
    
    def _check_field_conflicts(self, node: CableRouteNode) -> List[str]:
        """检查字段冲突
        
        检测节点内部字段是否自相矛盾
        
        Args:
            node: 节点对象
            
        Returns:
            List[str]: 冲突字段列表
        """
        conflicts = []
        
        # 检查距离单位一致性
        if node.distance is not None and node.distance_unit is None:
            conflicts.append("distance_unit")
        
        # 检查节点编号自相矛盾 (如 node_id 和 prev_node 相同)
        if node.node_id and node.prev_node:
            if node.node_id == node.prev_node:
                conflicts.append("prev_node")
        
        if node.node_id and node.next_node:
            if node.node_id == node.next_node:
                conflicts.append("next_node")
        
        return conflicts
    
    def _check_anomalies(self, node: CableRouteNode) -> List[str]:
        """检查异常值
        
        检测字段值是否异常
        
        Args:
            node: 节点对象
            
        Returns:
            List[str]: 异常字段列表
        """
        anomalies = []
        
        # 检查距离为负数
        if node.distance is not None and node.distance < 0:
            anomalies.append("distance")
        
        if node.slack_length is not None and node.slack_length < 0:
            anomalies.append("slack_length")
        
        # 检查光纤芯数为负数或过大
        if node.fiber_count is not None:
            if node.fiber_count <= 0:
                anomalies.append("fiber_count")
            elif node.fiber_count > 1000:  # 超过 1000 芯可能异常
                anomalies.append("fiber_count")
        
        # 检查置信度本身
        if node.confidence < 0.3:
            anomalies.append("confidence")
        
        return anomalies
    
    def _check_missing_fields(self, node: CableRouteNode) -> List[str]:
        """检查缺失字段
        
        检测非必填但期望有的字段
        
        Args:
            node: 节点对象
            
        Returns:
            List[str]: 缺失字段列表
        """
        missing = []
        
        # 期望字段 (非必填，但最好有)
        expected_fields = [
            "distance",
            "prev_node",
            "next_node"
        ]
        
        for field in expected_fields:
            value = getattr(node, field)
            if value is None or value == "":
                missing.append(field)
        
        return missing
    
    def _cross_check_nodes(self, nodes: List[CableRouteNode]):
        """跨节点校核
        
        检测节点间的关系是否一致
        
        Args:
            nodes: 节点列表
            
        校核内容:
            1. A 的 next_node 是 B，则 B 的 prev_node 应该是 A
            2. 节点编号唯一性
            3. 连接关系一致性
        """
        # 建立 node_id 到节点的映射
        node_map: Dict[str, CableRouteNode] = {}
        for node in nodes:
            if node.node_id:
                node_map[node.node_id] = node
        
        # 检查连接关系一致性
        for node in nodes:
            if not node.node_id:
                continue
            
            # 检查 next_node 的 prev_node
            if node.next_node:
                next_node_obj = node_map.get(node.next_node)
                if next_node_obj and next_node_obj.prev_node != node.node_id:
                    # 关系不一致，标记需要 review
                    node.review_required = True
                    if "next_node" not in node.uncertain_fields:
                        node.uncertain_fields.append("next_node")
                    node.confidence = max(0.0, node.confidence - 0.1)
            
            # 检查 prev_node 的 next_node
            if node.prev_node:
                prev_node_obj = node_map.get(node.prev_node)
                if prev_node_obj and prev_node_obj.next_node != node.node_id:
                    # 关系不一致，标记需要 review
                    node.review_required = True
                    if "prev_node" not in node.uncertain_fields:
                        node.uncertain_fields.append("prev_node")
                    node.confidence = max(0.0, node.confidence - 0.1)
    
    def calculate_review_statistics(
        self,
        nodes: List[CableRouteNode]
    ) -> Dict[str, Any]:
        """计算校核统计信息
        
        Args:
            nodes: 节点列表
            
        Returns:
            Dict[str, Any]: 统计信息
        """
        if not nodes:
            return {
                "total_nodes": 0,
                "review_count": 0,
                "low_confidence_count": 0,
                "avg_confidence": 0.0,
                "missing_fields_count": 0
            }
        
        review_count = sum(1 for n in nodes if n.review_required)
        low_confidence_count = sum(1 for n in nodes if n.confidence < self.confidence_threshold)
        avg_confidence = sum(n.confidence for n in nodes) / len(nodes)
        missing_fields_count = sum(len(n.uncertain_fields) for n in nodes)
        
        return {
            "total_nodes": len(nodes),
            "review_count": review_count,
            "low_confidence_count": low_confidence_count,
            "avg_confidence": round(avg_confidence, 3),
            "missing_fields_count": missing_fields_count
        }
    
    def validate_extraction_response(
        self,
        response: ExtractionResponse
    ) -> ExtractionResponse:
        """校核抽取响应
        
        对抽取响应中的所有节点进行校核
        
        Args:
            response: 抽取响应
            
        Returns:
            ExtractionResponse: 校核后的响应
        """
        # 校核所有节点
        checked_nodes = self.check_nodes(response.nodes)
        
        # 更新响应
        response.nodes = checked_nodes
        response.total_nodes = len(checked_nodes)
        response.review_count = sum(1 for n in checked_nodes if n.review_required)
        response.low_confidence_count = sum(1 for n in checked_nodes if n.confidence < self.confidence_threshold)
        
        return response


# 便捷函数

def check_nodes(nodes: List[CableRouteNode]) -> List[CableRouteNode]:
    """便捷函数：校核节点列表
    
    Args:
        nodes: 节点列表
        
    Returns:
        List[CableRouteNode]: 校核后的节点列表
    """
    service = RuleCheckService()
    return service.check_nodes(nodes)


def check_single_node(node: CableRouteNode) -> CableRouteNode:
    """便捷函数：校核单个节点
    
    Args:
        node: 节点对象
        
    Returns:
        CableRouteNode: 校核后的节点
    """
    service = RuleCheckService()
    return service.check_single_node(node)


def validate_extraction_response(response: ExtractionResponse) -> ExtractionResponse:
    """便捷函数：校核抽取响应
    
    Args:
        response: 抽取响应
        
    Returns:
        ExtractionResponse: 校核后的响应
    """
    service = RuleCheckService()
    return service.validate_extraction_response(response)
