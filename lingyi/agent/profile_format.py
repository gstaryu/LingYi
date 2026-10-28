"""患者画像格式化 - 统一渲染 prompt 片段。

此前 5 处（diagnosis / treatment / specialists / safety_reviewer / synthesis）各自拼
f-string，新增字段时容易漏改。集中到这里，保证字段同步、格式一致。

约定：
- 未采集的字段不输出（不写"未知"占位，避免模型把占位当事实）
- 空画像返回空串，调用方用 `if text:` 判断是否注入
"""

from typing import Any

_GENDER_LABEL = {"male": "男", "female": "女"}
_MAX_PAST_RECORDS = 3


def format_profile(profile: dict[str, Any] | None, *, indent: str = "  ") -> str:
    """把 state["patient_profile"] 渲染为 prompt 片段；无有效信息时返回空串。"""
    if not profile:
        return ""

    lines: list[str] = []

    age = profile.get("age")
    gender = _GENDER_LABEL.get(str(profile.get("gender") or ""), "")
    age_gender = "、".join(
        part for part in (f"{age} 岁" if age else "", gender) if part
    )
    if age_gender:
        lines.append(f"年龄/性别: {age_gender}")

    constitution = str(profile.get("constitution") or "").strip()
    if constitution and constitution != "未知":
        lines.append(f"体质: {constitution}")

    allergies = str(profile.get("allergies") or "").strip()
    if allergies and allergies != "无":
        lines.append(f"过敏史: {allergies}")

    medical_history = _format_medical_history(profile.get("medical_history") or [])
    if medical_history:
        lines.append(f"既往病史: {medical_history}")

    past = [str(x).strip() for x in (profile.get("past_history") or []) if str(x).strip()]
    if past:
        lines.append(f"既往诊疗: {', '.join(past[-_MAX_PAST_RECORDS:])}")

    if not lines:
        return ""

    body = "\n".join(f"{indent}{line}" for line in lines)
    return f"患者画像:\n{body}"


def _format_medical_history(items: list) -> str:
    """把病史条目渲染为"高血压（2018 年起，现患）、阑尾切除（既往）"。"""
    rendered: list[str] = []
    for item in items:
        if isinstance(item, str):
            if item.strip():
                rendered.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        status = "既往" if item.get("status") == "history" else "现患"
        since = item.get("since_year")
        if isinstance(since, int):
            rendered.append(f"{name}（{since} 年起，{status}）")
        else:
            rendered.append(f"{name}（{status}）")
    return "、".join(rendered)
