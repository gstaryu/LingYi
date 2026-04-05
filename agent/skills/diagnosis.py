import os
from langchain_core.messages import SystemMessage
from agent.state import AgentState
from model_provider import model_manager
from config import config


def diagnosis_node(state: AgentState):
    """
    辨证节点：执行中医“理、法”推演。
    已强化对上传文件解析内容的感知逻辑，并优化了面对纯报告数据时的临床推演深度。
    """
    print("--- 进入辨证流程 ---")

    # 1. 加载技能规格 (Markdown Prompt)
    skill_dir = os.path.dirname(__file__)
    md_path = os.path.join(skill_dir, "diagnosis.md")

    # 鲁棒性检查：如果 md 文件不存在，使用内置的基础 Prompt
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            prompt_content = f.read()
    else:
        prompt_content = "你是一个中医专家，请根据症状和资料进行辨证论治，输出【理】病机分析和【法】治则治法。"

    # 2. 整合多维上下文信息
    symptoms = state.get("symptoms", [])
    docs = state.get("retrieved_docs", [])
    file_content = state.get("extracted_file_content", "")  # 获取由 reader 节点解析出的文件内容
    profile = state.get("patient_profile", {})  # 获取患者长期画像（体质、过敏史等）

    # 构造知识库参考上下文
    docs_context = "\n".join([f"- 参考资料: {d}" for d in docs]) if docs else "无相关检索文献"

    # 3. 构造强化版系统提示词
    # 重点：将文件解析内容、长期画像与当前症状进行深度整合
    full_prompt = f"""
{prompt_content}

=== 临床参考背景 (核心依据) ===
【患者长期画像】: 
- 体质: {profile.get('constitution', '未知')}
- 过敏史: {profile.get('allergies', '无')}
- 既往史: {profile.get('past_history', '无')}

【上传的文件/报告解析结果】: 
{file_content if file_content else "本次未上传参考文件"}

【当前识别到的核心症状】: 
{', '.join(symptoms) if symptoms else "用户尚未描述具体症状，请重点参考上述文件内容"}

【检索到的中医典籍参考】: 
{docs_context}

=== 任务指令 ===
1. 请结合上述所有背景资料，执行中医“理、法”推演。
2. 如果用户仅提供了体检报告（如转氨酶偏高）而未描述症状，请运用中医“治未病”或“辨指标”的思想，分析该指标在经络脏腑（如肝胆）层面的潜在失调。
3. 严禁声称“无法查看文件”，你必须基于解析出的文字内容进行深度分析。
4. 辨证结论必须专业，逻辑严密，为后续的【方、药】输出提供坚实依据。
5. 【重要】动态辨证连贯性：如果这是患者在对话中追加的症状（复诊），请务必在原有辨证思路上进行加减微调，切勿因为一个新症状就彻底推翻先前的整个辨证逻辑（例如从麻黄汤突变为三仁汤），以保证诊断的连续性。
"""

    # 4. 调用大模型
    llm = model_manager.get_model()
    # 携带最近 N 轮对话上下文，确保对话的连贯性
    history_window = config.MAX_HISTORY_MESSAGES_DIAGNOSIS
    response = llm.invoke([SystemMessage(content=full_prompt)] + state["messages"][-history_window:])

    # 5. 更新状态字典：将辨证结果存入 diagnosis 字段
    # Diagnosis 节点不用向用户展示，只是内部流转给 treatment
    # 因此不需要添加到 messages 里，避免重复输出
    return {
        "diagnosis": response.content,
    }