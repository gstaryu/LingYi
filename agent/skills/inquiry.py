import os
import json
import re
from langchain_core.messages import SystemMessage
from agent.state import AgentState
from model_provider import model_manager
from config import config


def _find_first_json_object_span(text: str) -> tuple[int, int] | None:
    """Return (start, end_exclusive) of the first top-level JSON object in text.

    This is a small brace-matching scanner that tolerates arbitrary prefixes/suffixes
    (like disclaimers) and ignores braces inside JSON strings.
    """
    if not text:
        return None

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]

        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return (start, i + 1)

    return None


def _extract_json_object(text: str) -> dict:
    """Extract a JSON object from messy LLM output.

    Priority:
    1) ```json ... ``` fenced block
    2) first balanced {...} object found by scanner
    3) direct json.loads

    Returns {} if parsing fails.
    """
    if not isinstance(text, str) or not text.strip():
        return {}

    # 1) Markdown fenced json block
    fenced = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 2) First balanced object
    span = _find_first_json_object_span(text)
    if span:
        candidate = text[span[0]:span[1]].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 3) Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _strip_json_object(text: str) -> str:
    """Remove the first JSON object from text, keep surrounding human/disclaimer text."""
    if not isinstance(text, str) or not text:
        return ""

    # Remove fenced block first
    fenced = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return (text[:fenced.start()] + text[fenced.end():]).strip()

    span = _find_first_json_object_span(text)
    if not span:
        return text.strip()

    return (text[:span[0]] + text[span[1]:]).strip()


def inquiry_node(state: AgentState):
    """
    问诊节点：判定信息完备性。
    """
    skill_dir = os.path.dirname(__file__)
    md_path = os.path.join(skill_dir, "inquiry.md")
    with open(md_path, "r", encoding="utf-8") as f:
        inquiry_prompt = f.read()

    llm = model_manager.get_model()

    # 1. 提取上下文
    file_content = state.get("extracted_file_content", "")
    summary = state.get("summary", "")
    existing_symptoms = ", ".join(state.get("symptoms", []))
    has_provided_treatment = state.get("has_provided_treatment", False)

    context_block = f"\n\n=== 核心上下文 ===\n已提取症状: [{existing_symptoms}]\n已给出初步方案: {'是(用户当前可能在追加症状或提问，请直接辨证解答)' if has_provided_treatment else '否(处于初诊收集阶段)'}"
    if file_content: context_block += f"\n【文件内容】: {file_content}"
    if summary: context_block += f"\n【历史摘要】: {summary}"

    # 2. 调用模型
    system_msg = SystemMessage(content=f"{inquiry_prompt}\n{context_block}")

    try:
        # 只带入最近 N 轮对话，保证效率
        history_window = config.MAX_HISTORY_MESSAGES_INQUIRY
        messages = state["messages"][-history_window:]

        response = llm.invoke([system_msg] + messages)
        content = response.content or ""

        # 稳健的 JSON 解析（允许前后缀存在免责声明/多余文本）
        res_data = _extract_json_object(content)

        if not res_data:
            # 再兜底，当完全解析不出 JSON 时，强行按 chat 回馈，附带文本提取的症状
            res_data = {"intent_type": "chat", "is_complete": False, "symptoms": [], "response": content}

        intent = res_data.get("intent_type", "chat")

        # 覆写 AI 响应文本：优先使用 JSON 字段里的 response；若缺失则剥离 JSON 后展示剩余文本
        response_text = res_data.get("response")
        if isinstance(response_text, str) and response_text.strip():
            response.content = response_text
        else:
            response.content = _strip_json_object(content) or content

        # 3. 将新提取的症状和已有的合并
        symptoms = state.get("symptoms", [])
        new_symptoms = res_data.get("symptoms", [])
        merged_symptoms = list(set(symptoms + new_symptoms))

        is_complete = res_data.get("is_complete", False)

        # 兜底强制放行：如果已经给过方案，或者是复诊调方，强行进入辨证环节，不再死缠烂打追问
        if has_provided_treatment:
            is_complete = True
            if intent == "inquiry_more":
                intent = "diagnose"

        # 路由降级逻辑：如果是诊疗但信息不全，标记为继续问诊
        if intent == "diagnose" and not is_complete:
            intent = "inquiry_more"

        # 如果是结尾客套话（用户发“谢谢”、“好的”），重置或保持 chat 意图以直接返回
        last_user_msg = ""
        for m in reversed(messages):
            if m.type == "human":
                last_user_msg = m.content
                break

        if intent in ["diagnose", "inquiry_more"] and any(word in last_user_msg for word in ["谢谢", "感谢", "好的", "再见", "拜拜"]):
            intent = "chat"

        if not response.content:
            response.content = "好的"

        return {
            "intent_type": intent,
            "symptoms": merged_symptoms,
            "messages": [response]
        }
    except Exception as e:
        print(f"❌ Inquiry 解析失败: {e}")
        # 发生异常时退化为 chat 意图，确保流程不挂死
        return {"intent_type": "chat"}