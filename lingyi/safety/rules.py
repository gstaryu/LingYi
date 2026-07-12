"""
中医安全审查引擎 — 物理校验"十八反"、"十九畏"配伍禁忌。

设计原则:
- 纯 Python 规则引擎，不依赖 LLM 或外部服务
- 通过构造函数注入，不使用模块级单例
- 支持双向匹配（"丁香畏郁金"也意味着"郁金畏丁香"）
- 使用关键词包含判断增加鲁棒性（如"生甘草"也能匹配"甘草"）
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SafetyEngine:
    """
    中医配伍禁忌安全引擎。

    集成"十八反"和"十九畏"两套传统中药配伍禁忌规则，
    对药方中的药材进行两两交叉检查，发现冲突即返回错误信息。
    """

    # 【十八反】完整数据
    # 逻辑：Key 反 对饮列表
    EIGHTEEN_ANTAGONISMS: dict[str, list[str]] = {
        "甘草": ["海藻", "大戟", "甘遂", "芫花"],
        "乌头": ["半夏", "瓜蒌", "瓜蒌皮", "瓜蒌仁", "贝母", "川贝", "浙贝", "白蔹", "白及"],
        "川乌": ["半夏", "瓜蒌", "瓜蒌皮", "瓜蒌仁", "贝母", "川贝", "浙贝", "白蔹", "白及"],
        "草乌": ["半夏", "瓜蒌", "瓜蒌皮", "瓜蒌仁", "贝母", "川贝", "浙贝", "白蔹", "白及"],
        "附子": ["半夏", "瓜蒌", "瓜蒌皮", "瓜蒌仁", "贝母", "川贝", "浙贝", "白蔹", "白及"],
        "藜芦": [
            "人参", "党参", "沙参", "南沙参", "北沙参",
            "丹参", "玄参", "细辛", "芍药", "赤芍", "白芍",
        ],
    }

    # 【十九畏】完整数据
    NINETEEN_INHIBITIONS: dict[str, list[str]] = {
        "硫黄": ["芒硝", "玄明粉"],
        "水银": ["砒霜"],
        "狼毒": ["密陀僧"],
        "巴豆": ["牵牛子", "黑丑", "白丑"],
        "丁香": ["郁金"],
        "芒硝": ["三棱"],
        "牙硝": ["三棱"],
        "川乌": ["犀角", "水牛角"],
        "草乌": ["犀角", "水牛角"],
        "官桂": ["石脂", "赤石脂"],
        "肉桂": ["石脂", "赤石脂"],
        "人参": ["五灵脂"],
    }

    def __init__(self):
        """初始化安全引擎，合并十八反和十九畏为统一规则表。"""
        # 合并所有禁忌规则，便于统一遍历
        self._all_rules: dict[str, list[str]] = {
            **self.EIGHTEEN_ANTAGONISMS,
            **self.NINETEEN_INHIBITIONS,
        }
        logger.info(
            "SafetyEngine 初始化完成: 十八反 %d 条, 十九畏 %d 条",
            len(self.EIGHTEEN_ANTAGONISMS),
            len(self.NINETEEN_INHIBITIONS),
        )

    def check_prescription(self, herb_list: list[str]) -> tuple[bool, Optional[str]]:
        """
        校验药方是否包含禁忌药对（同时检查十八反与十九畏）。

        Args:
            herb_list: 药材名称列表

        Returns:
            (is_safe, error_msg)
            - is_safe=True 时 error_msg 为 None
            - is_safe=False 时 error_msg 包含冲突描述
        """
        found_conflicts: list[str] = []

        # 两两交叉检查所有药材对
        for i, herb_a in enumerate(herb_list):
            for j in range(i + 1, len(herb_list)):
                herb_b = herb_list[j]

                # 检查 A 是否在 B 的禁忌名单里，或者 B 是否在 A 的禁忌名单里
                for key, forbidden_list in self._all_rules.items():
                    # 正向检查：herb_a 匹配 key，herb_b 匹配 forbidden
                    if key in herb_a:
                        for f_herb in forbidden_list:
                            if f_herb in herb_b:
                                found_conflicts.append(
                                    f"【{herb_a}】与【{herb_b}】存在配伍禁忌"
                                )

                    # 反向检查：herb_b 匹配 key，herb_a 匹配 forbidden
                    if key in herb_b:
                        for f_herb in forbidden_list:
                            if f_herb in herb_a:
                                found_conflicts.append(
                                    f"【{herb_b}】与【{herb_a}】存在配伍禁忌"
                                )

        # 去重处理
        unique_conflicts = list(set(found_conflicts))

        if unique_conflicts:
            error_msg = "；".join(unique_conflicts)
            logger.warning("药方安全校验失败: %s", error_msg)
            return False, error_msg

        return True, None

    def get_rules_text(self) -> str:
        """
        获取完整的禁忌规则文本，用于注入 LLM prompt。

        Returns:
            格式化的规则文本
        """
        lines = ["【十八反】"]
        for key, forbiddens in self.EIGHTEEN_ANTAGONISMS.items():
            lines.append(f"  {key} 反 {', '.join(forbiddens)}")

        lines.append("\n【十九畏】")
        for key, forbiddens in self.NINETEEN_INHIBITIONS.items():
            lines.append(f"  {key} 畏 {', '.join(forbiddens)}")

        return "\n".join(lines)
