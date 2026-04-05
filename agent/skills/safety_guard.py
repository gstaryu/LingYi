import os
import json
import re
from langchain_core.messages import SystemMessage, AIMessage
from agent.state import AgentState
from model_provider import model_manager

def safety_guard_node(state: AgentState):
    """
    独立安全守卫节点：检查用户的最近输入是否要求添加违规配伍药材。
    如果发现违禁药材，拦截请求并直接生成拒绝和科普的消息，跳过后续的正常问诊和处方阶段。
    """
    skill_dir = os.path.dirname(__file__)
    md_path = os.path.join(skill_dir, "safety_guard.md")
    with open(md_path, "r", encoding="utf-8") as f:
        safety_prompt = f.read()

    llm = model_manager.get_model()

    # 获取最新的消息（用户输入）和前面的部分历史用于比对
    history_window = 10
    messages = state["messages"][-history_window:]

    system_msg = SystemMessage(content=safety_prompt)

    response = llm.invoke([system_msg] + messages)
    content = response.content

    json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
    if not json_match:
        json_match = re.search(r'(\{.*})', content, re.DOTALL)

    res_data = {}
    if json_match:
        # 清理可能导致 JSON 解析失败的无关文本或转义换行
        # 使用更为健壮的加载策略
        clean_json_str = json_match.group(1).strip()
        try:
            res_data = json.loads(clean_json_str)
        except json.JSONDecodeError:
            # 兼容模型错误输出 true/false 混入中文字符的特殊情况
            if '"has_violation": true' in clean_json_str or '"has_violation":true' in clean_json_str:
                res_data["has_violation"] = True

                # 简单剥离 violation_reason
                reason_match = re.search(r'"violation_reason":\s*"(.*?)"', clean_json_str, re.DOTALL)
                res_data["violation_reason"] = reason_match.group(1) if reason_match else "存在严重配伍禁忌。"

    has_violation = res_data.get("has_violation", False)
    violation_reason = res_data.get("violation_reason", "")

    if has_violation:
        # 如果判定有配伍禁忌风险，直接生成一段严厉科普的话语写入历史，并打上违规标记

        rejection_message = (
            f"【⚠️ 严重的配伍禁忌警告】\n\n"
            f"您刚刚提出的配伍请求是非常危险的！在中医配伍禁忌（即十八反、十九畏）等规则中，明确指出：\n"
            f"**{violation_reason}**\n\n"
            f"一旦同时服用，可能会产生严重的毒副作用或抵消药效。为了您的安全，我绝对不能将这味药加入您当前的方剂中。"
            f"请继续使用原方，并在正规中医师的当面指导下进行调整！"
        )

        # 伪装成一次完整的拦截对话
        safety_response = AIMessage(content=rejection_message)

        return {
            "safety_violation_msg": rejection_message,
            "messages": [safety_response],
            "intent_type": "safety_rejected"  # 设定特殊的 intent，直接引向末尾结束
        }

    # 如果安全就清空此标记并放行
    return {
        "safety_violation_msg": None,
        "intent_type": "chat"
    }
