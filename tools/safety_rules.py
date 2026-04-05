from typing import List, Tuple, Optional


class SafetyEngine:
    """
    中医安全审查引擎：物理校验“十八反”、“十九畏”。
    """

    # 【十八反】 完整数据
    # 逻辑：Key 反 对饮列表
    EIGHTEEN_ANTAGONISMS = {
        "甘草": ["海藻", "大戟", "甘遂", "芫花"],
        "乌头": ["半夏", "瓜蒌", "瓜蒌皮", "瓜蒌仁", "贝母", "川贝", "浙贝", "白蔹", "白及"],
        "川乌": ["半夏", "瓜蒌", "瓜蒌皮", "瓜蒌仁", "贝母", "川贝", "浙贝", "白蔹", "白及"],
        "草乌": ["半夏", "瓜蒌", "瓜蒌皮", "瓜蒌仁", "贝母", "川贝", "浙贝", "白蔹", "白及"],
        "附子": ["半夏", "瓜蒌", "瓜蒌皮", "瓜蒌仁", "贝母", "川贝", "浙贝", "白蔹", "白及"],
        "藜芦": ["人参", "党参", "沙参", "南沙参", "北沙参", "丹参", "玄参", "细辛", "芍药", "赤芍", "白芍"]
    }

    # 【十九畏】 完整数据
    NINETEEN_INHIBITIONS = {
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
        "人参": ["五灵脂"]
    }

    @classmethod
    def check_prescription(cls, herb_list: List[str]) -> Tuple[bool, Optional[str]]:
        """
        校验药方是否包含禁忌药对（同时检查十八反与十九畏）
        """
        found_conflicts = []

        # 将所有禁忌组合并到一个检查字典中，方便统一遍历
        all_rules = {**cls.EIGHTEEN_ANTAGONISMS, **cls.NINETEEN_INHIBITIONS}

        # 1. 建立一个易于检索的双向映射集合（对称性检查）
        # 因为禁忌是双向的，例如“丁香畏郁金”也意味着“郁金畏丁香”
        for i, herb_a in enumerate(herb_list):
            for j in range(i + 1, len(herb_list)):
                herb_b = herb_list[j]

                # 检查 A 是否在 B 的禁忌名单里，或者 B 是否在 A 的禁忌名单里
                # 使用关键词包含判断，增加鲁棒性（如“生甘草”也能匹配“甘草”）
                for key, forbidden_list in all_rules.items():
                    if key in herb_a:  # 如果药 A 匹配到禁忌 Key
                        for f_herb in forbidden_list:
                            if f_herb in herb_b:
                                found_conflicts.append(f"【{herb_a}】与【{herb_b}】存在配伍禁忌")

                    if key in herb_b:  # 如果药 B 匹配到禁忌 Key
                        for f_herb in forbidden_list:
                            if f_herb in herb_a:
                                found_conflicts.append(f"【{herb_b}】与【{herb_a}】存在配伍禁忌")

        # 去重处理
        unique_conflicts = list(set(found_conflicts))

        if unique_conflicts:
            return False, "；".join(unique_conflicts)
        return True, None


# 导出实例
safety_engine = SafetyEngine()