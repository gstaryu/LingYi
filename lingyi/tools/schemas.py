"""
工具参数 Schema - 每个领域工具的 Pydantic 输入模型。

LangGraph/LangChain 的 StructuredTool 通过 args_schema 向 LLM 暴露工具参数结构，
LLM 据此生成符合 schema 的工具调用。所有字段使用 Pydantic v2 BaseModel。
"""

from pydantic import BaseModel, Field


class SearchTcmClassicsInput(BaseModel):
    """检索中医经典古籍。"""

    query: str = Field(
        ...,
        description="检索关键词或证候描述，例如 '太阳病中风' 或 '桂枝汤证'",
        min_length=1,
    )


class LookupHerbInput(BaseModel):
    """按正名精确查询本草信息。"""

    name: str = Field(
        ...,
        description="药材正名，例如 '人参'、'黄芪'、'甘草'",
        min_length=1,
    )


class SearchHerbsInput(BaseModel):
    """按关键词模糊搜索本草。"""

    query: str = Field(
        ...,
        description="搜索关键词（症状/功效/药名），如 '腹胀'、'补气'",
        min_length=1,
    )


class SearchFormulasInput(BaseModel):
    """按证候或关键词搜索方剂。"""

    query: str = Field(
        ...,
        description="证候或关键词，例如 '太阳中风' 或 '桂枝汤'",
        min_length=1,
    )


class CheckHerbSafetyInput(BaseModel):
    """校验药方配伍安全（十八反十九畏）。"""

    herbs: list[str] = Field(
        ...,
        description="药材名称列表，例如 ['甘草', '甘遂']",
        min_length=1,
    )


class GetPatientProfileInput(BaseModel):
    """获取患者画像（体质、过敏史、既往记录）。"""

    patient_id: str = Field(
        ...,
        description="患者 ID（通常等于 username）",
        min_length=1,
    )


class SavePatientProfileInput(BaseModel):
    """保存/更新患者画像（仅传入非空字段才更新）。"""

    patient_id: str = Field(
        ...,
        description="患者 ID（通常等于 username）",
        min_length=1,
    )
    constitution: str = Field(
        default="",
        description="体质类型（如阳虚、阴虚、痰湿等）；留空表示不更新",
    )
    allergies: str = Field(
        default="",
        description="过敏史（如 '青霉素、海鲜'）；留空表示不更新",
    )


class WebSearchInput(BaseModel):
    """搜索互联网获取最新信息。"""

    query: str = Field(
        ...,
        description="搜索关键词或问题",
        min_length=2,
        max_length=500,
    )
