import os
import json
import re
from langchain_core.messages import SystemMessage
from agent.state import AgentState
from model_provider import model_manager
from tools.safety_rules import safety_engine
from config import config


def extract_json(text: str):
    """
    健壮的 JSON 提取函数，支持从包含杂述的文本中提取 JSON 块。
    """
    try:
        # 1. 尝试寻找 Markdown 块
        json_block = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_block:
            return json.loads(json_block.group(1))

        # 2. 尝试寻找第一个 { 和最后一个 }
        json_match = re.search(r'(\{.*})', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        # 3. 直接解析
        return json.loads(text)
    except:
        return None

def strip_json_block(text: str) -> str:
    """
    清洗文本，将附加的 JSON 代码块从向用户展示的内容中剔除。
    """
    clean_text = re.sub(r'```json\s*\{.*?\s*```', '', text, flags=re.DOTALL)
    # 如果大模型没写 Markdown block 而是直接贴了字典
    clean_text = re.sub(r'\{.*?"herb_names".*?}', '', clean_text, flags=re.DOTALL)
    return clean_text.strip()

def treatment_node(state: AgentState):
    """
    加固型处方节点：支持安全报错的回馈，引导模型自我修正。
    """
    print("--- 进入处方生成流程 ---")
    skill_dir = os.path.dirname(__file__)
    md_path = os.path.join(skill_dir, "treatment.md")
    with open(md_path, "r", encoding="utf-8") as f:
        treatment_prompt = f.read()

    # 将安全禁忌名录直接注入到 prompt 中，加深模型印象
    from tools.safety_rules import SafetyEngine
    rules_text = "【附录：十八反十九畏完整清单，请严格比对，向用户科普并禁止违规配伍】\n十八反：" + str(SafetyEngine.EIGHTEEN_ANTAGONISMS) + "\n十九畏：" + str(SafetyEngine.NINETEEN_INHIBITIONS)

    # 获取重试次数
    retry_count = state.get("safety_retry_count", 0)

    # 1. 核心上下文与【安全报错注入】
    diagnosis_res = state.get("diagnosis", "")
    safety_errors = state.get("safety_errors")  # 获取上一轮拦截到的错误

    reference_context = f"\n\n【辨证分析结果】: {diagnosis_res}"
    if state.get("extracted_file_content"):
        reference_context += f"\n【参考文件内容】: {state.get('extracted_file_content')}"

    # 如果有安全错误，以最高优先级展示
    error_feedback = ""
    if safety_errors:
        error_feedback = f"\n\n⚠️ 【重要：安全拦截警报】\n上次生成遭遇以下错误：{safety_errors}。\n请严格按照要求在【疑问解答】中科普十八反/十九畏禁忌，并重新拟定彻底删除冲突药材的方子！"

    full_prompt = f"{treatment_prompt}{reference_context}{error_feedback}\n\n{rules_text}"

    llm = model_manager.get_model()
    history_window = config.MAX_HISTORY_MESSAGES_TREATMENT
    response = llm.invoke([SystemMessage(content=full_prompt)] + state["messages"][-history_window:])

    try:
        content = response.content
        res_data = extract_json(content)

        if res_data and isinstance(res_data, dict):
            herb_names = res_data.get("herb_names", [])

            # 物理校验
            is_safe, error_msg = safety_engine.check_prescription(herb_names)
            if not is_safe:
                return {"safety_errors": error_msg, "safety_retry_count": retry_count + 1, "messages": [response]}

            # 提取清洗掉JSON代码块后的纯文本并写回 messages
            clean_plan = strip_json_block(content)

            # 如果清洗完什么都没了，那就是大模型还是把所有东西塞进了 dictionary 中
            if not clean_plan and "treatment_plan" in res_data:
                clean_plan = res_data["treatment_plan"]

            response.content = clean_plan

            return {
                "treatment_plan": clean_plan,
                "safety_errors": None,  # 清空错误标记
                "safety_retry_count": 0,
                "has_provided_treatment": True,
                "messages": [response]
            }
        else:
            return {"safety_errors": "未检测到规范的 JSON 格式或字典结构，请重新生成。", "safety_retry_count": retry_count + 1, "messages": [response]}
    except Exception as e:
        return {"safety_errors": f"解析异常: {e}", "safety_retry_count": retry_count + 1, "messages": [response]}


def safety_check_logic(state: AgentState):
    retry_count = state.get("safety_retry_count", 0)
    if state.get("safety_errors"):
        if retry_count < config.SAFETY_MAX_RETRIES:
            return "re_treatment"
        else:
            print("⚠️ 处方生成多次违规/格式错误，强制结束（生产环境请阻断）")
            return "safe_to_end"
    return "safe_to_end"