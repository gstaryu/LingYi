"""
结构化知识库数据模型 - 本草、方剂、禁忌的数据结构。

设计原则（与 lingyi/storage/base.py 一致）:
- 使用 @dataclass 纯数据类，字段带 docstring
- list/dict 字段在 SQLite 层以 JSON TEXT 存储
- 构造函数注入，不依赖外部服务
"""

from dataclasses import dataclass, field


@dataclass
class Herb:
    """本草（中药）结构化信息。"""

    name: str
    """药材正名（如 人参、黄芪）。"""

    aliases: list[str] = field(default_factory=list)
    """别名列表（如 棒槌、园参）。"""

    nature_flavor: str = ""
    """性味（如 '甘，微温'）。"""

    meridians: list[str] = field(default_factory=list)
    """归经列表（如 ['脾', '肺']）。"""

    efficacy: str = ""
    """功效描述。"""

    indications: list[str] = field(default_factory=list)
    """主治病症列表。"""

    dosage: str = ""
    """用量（如 '3-9g'）。"""

    processing: str = ""
    """炮制方法。"""

    contraindications: str = ""
    """禁忌说明。"""


@dataclass
class FormulaComponent:
    """方剂组成中的单味药及其用量。"""

    herb: str
    """药材名称。"""

    dosage: str = ""
    """用量（如 '9g'）。"""


@dataclass
class Formula:
    """方剂结构化信息。"""

    name: str
    """方剂名称（如 桂枝汤）。"""

    source: str = ""
    """出处（如 '伤寒论'）。"""

    composition: list[FormulaComponent] = field(default_factory=list)
    """组成药物列表。"""

    indication: str = ""
    """主治证候。"""

    modifications: str = ""
    """加减法。"""

    contraindications: str = ""
    """禁忌。"""

    category: str = ""
    """分类（经方/时方）。"""


@dataclass
class Contraindication:
    """中药禁忌条目。"""

    herb: str
    """药材名称。"""

    type: str = ""
    """禁忌类型: 妊娠 / 体质 / 配伍。"""

    detail: str = ""
    """禁忌详情说明。"""

    severity: str = ""
    """严重程度: 禁用 / 慎用。"""
