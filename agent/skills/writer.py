import json
import re
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage
from agent.state import AgentState
from storage.profile_manager import profile_manager
from model_provider import model_manager


def writer_node(state: AgentState, config: RunnableConfig):
    """
    智能归档节点：不仅保存诊疗记录，还通过 LLM 自动更新患者的长期画像（体质、过敏史）。
    """
    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id", "default")

    diagnosis = state.get("diagnosis", "")
    treatment = state.get("treatment_plan", "")
    symptoms = state.get("symptoms", [])

    # 如果没有任何实质性诊疗内容，直接跳过更新
    if not diagnosis and not treatment:
        return {}

    print(f"--- 💾 正在执行智能归档与画像分析 (ID: {thread_id}) ---")

    # 1. 构造本次诊疗记录
    new_record = {
        "symptoms": symptoms,
        "diagnosis": diagnosis,
        "treatment": treatment
    }

    # 2. 调用 LLM 从本次对话中提取潜在的画像更新
    llm = model_manager.get_model()

    # 获取当前历史已有的过敏史以便于合并
    current_profile = state.get("patient_profile", {})
    existing_allergies = current_profile.get("allergies", "无")
    existing_constitution = current_profile.get("constitution", "未知")

    extract_prompt = f"""
    你是一个中医病历管理助手。请根据以下本次整个对话记录，分析并提取患者的长期特征。

    【整个对话历史（重要）】: {str([m.content for m in state.get('messages', [])[-10:]])}
    【系统已存在的过敏史记录】: {existing_allergies}
    【系统已存在的体质记录】: {existing_constitution}

    任务：
    1. 判定患者的“中医体质”（如：气虚质、湿热质、平和质等）。
    2. 提取提及到的“过敏史”（如：对青霉素过敏）。

    注意：
    - 如果内容不足以判断体质，体质请保留为“未知”。如果无法判断且系统已有记录，则输出系统已有记录。
    - 如果对话历史中提及了过敏药物（如用户说了“可是我对薏苡仁过敏”等明确过敏史），必须提取出来！
    - 如果系统中已存在过敏史，并且在此次对话中又发现了新的过敏药物，必须将新的和旧的结合输出（例如：“对青霉素、薏苡仁过敏”）。
    - 结合的逻辑是：只要不是“无”，就务必将最新的过敏记录明确提取。

    必须输出 JSON 格式：
    {{
      "constitution": "提取的体质",
      "allergies": "提取的过敏史"
    }}
    """

    try:
        response = llm.invoke([SystemMessage(content=extract_prompt)])
        # 清洗并解析 JSON
        json_match = re.search(r'(\{.*})', response.content, re.DOTALL)
        profile_updates = json.loads(json_match.group(1)) if json_match else {}

        # 3. 合并新记录与提取出的特征，写入数据库
        # profile_manager.update_profile 会自动处理逻辑：
        # - 如果 profile_updates 有值且不为"未知/无"，则覆盖旧值
        # - new_record 会被追加到历史列表中
        update_data = {
            "new_record": new_record,
            "constitution": profile_updates.get("constitution", "未知"),
            "allergies": profile_updates.get("allergies", "无")
        }

        # 过滤掉默认值，防止由于 LLM 的保守导致有效旧数据被“未知”覆盖
        final_update = {"new_record": new_record}
        if update_data["constitution"] != "未知":
            final_update["constitution"] = update_data["constitution"]
        if update_data["allergies"] != "无":
            final_update["allergies"] = update_data["allergies"]

        profile_manager.update_profile(thread_id, final_update)
        print(f"✅ 诊疗记录已存入历史，画像特征已同步更新。")

    except Exception as e:
        print(f"⚠️ 画像分析失败，执行基础记录归档: {e}")
        profile_manager.update_profile(thread_id, {"new_record": new_record})

    return {}


def mem_recall_node(state: AgentState, config: RunnableConfig):
    """
    加载长期记忆节点（保持不变）。
    """
    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id", "default")

    print(f"--- 🧠 正在调取患者记忆 (ID: {thread_id}) ---")
    profile = profile_manager.get_profile(thread_id)

    return {"patient_profile": profile}