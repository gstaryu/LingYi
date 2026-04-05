import os
from langchain_core.messages import SystemMessage
from agent.state import AgentState
from model_provider import model_manager
from tools.vector_db_client import vector_client
from config import config
from typing import Any


def rag_search_node(state: AgentState) -> dict[str, Any]:
    """
    负责在中医文献库中检索相关书籍与症状。
    """
    symptoms = state.get("symptoms", [])
    query = " ".join(symptoms) if symptoms else state["messages"][-1].content

    # 获取当前的重试次数，若是第一次进入，则是 0
    current_retry_count = state.get("rag_retry_count", 0)

    print("\n" + "展开 RAG 检索结果 ".center(50, "="))
    print(f"📡 检索关键词: {query} (当前重试次数: {current_retry_count})")

    # ====== 阶段一：粗排召回 (Recall) ======
    try:
        search_results = vector_client.hybrid_search(query, n_results=config.RAG_RECALL_K)
    except Exception as e:
        print(f"❌ 检索失败: {e}")
        return {"retrieved_docs": [], "rag_retry_count": current_retry_count + 1}

    print(f"📥 粗排召回 {len(search_results)} 条候选典籍证据。")

    # ====== 阶段二：精排过滤 (Rerank) ======
    reranker = model_manager.get_reranker()
    if reranker and len(search_results) > 0:
        print("🔄 正在执行深度语义重排 (Rerank)...")
        # 组装 query 与 document 的输入对
        pairs = [[query, res["content"]] for res in search_results]

        # 交叉测算得分
        try:
            scores = reranker.predict(pairs)
            for i, res in enumerate(search_results):
                res["rerank_score"] = float(scores[i])

            # 按 rerank 分数降序排列
            search_results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        except Exception as e:
            print(f"⚠️ 重排计算过程发生异常，回退到原顺序: {e}")

    # ====== 阶段三：截断与组装 ======
    search_results = search_results[:config.RAG_RERANK_K]

    retrieved_docs = []
    print(f"🎯 重排完成，保留精准度最高的前 {len(search_results)} 条证据：")

    for i, res in enumerate(search_results):
        content = res["content"]
        source = res["metadata"].get("source", "未知典籍")

        # 如果重排了就显示重排分，否则显示原召回分
        display_score = res.get("rerank_score", res.get("score", 0.0))

        # 构造存储字符串
        doc_entry = f"【出处：{source}】{content}"
        retrieved_docs.append(doc_entry)

        # 打印前 3 条最相关的证据到控制台，方便调试观察
        if i < 3:
            print(f"\n[{i + 1}] 相关度/重排分: {display_score:.4f} | 来源: {source}")
            # 限制打印长度，避免刷屏
            display_text = content[:150] + "..." if len(content) > 150 else content
            print(f"📖 内容: {display_text}")

    print("=" * 50 + "\n")

    return {
        "retrieved_docs": retrieved_docs,
        "rag_retry_count": current_retry_count + 1,
        # Default score, will be updated by grader
        "rag_score": 0.0
    }


def rag_grader_node(state: AgentState):
    """
    评估检索到的文献是否能够支撑当前症状的辨证。
    """
    print("⚖️ 正在评估检索结果质量...")
    docs = state.get("retrieved_docs", [])
    if not docs:
        print("📊 评估得分: 0.0 (无检索结果)")
        return {"rag_score": 0.0}

    symptoms = state.get("symptoms", [])
    symptoms_str = "、".join(symptoms) if symptoms else "未提供"
    docs_str = "\n".join(docs)

    prompt = f"""
    你是一个专业的中医文献评估助手。
    当前患者症状：{symptoms_str}
    检索到的中医文献片段：
    {docs_str}
    
    请仔细评估上述文献与当前患者症状的匹配度、以及对辨证论治是否有实际指导意义。
    请直接输出一个 0.0 到 1.0 之间的小数作为评分（例如：0.8），不要输出任何其他多余文本。
    """

    llm = model_manager.get_model()
    try:
        response = llm.invoke([SystemMessage(content=prompt)])
        # 从输出中提取小数
        import re
        match = re.search(r'(0\.\d+|1\.0)', response.content)
        if match:
            score = float(match.group(1))
        else:
            score = 0.5  # 回退保守分
    except Exception as e:
        print(f"❌ 评估节点模型调用异常: {e}")
        score = 0.5

    print(f"📊 评估得分: {score}")
    return {"rag_score": score}


def rag_rewrite_node(state: AgentState):
    """
    重写查询节点：当检索结果不佳时，将通俗症状转为更专业的中医术语。
    """
    print("🔄 检索质量不足，正在重写查询症状...")
    symptoms = state.get("symptoms", [])
    symptoms_str = "、".join(symptoms) if symptoms else state["messages"][-1].content

    prompt = f"""
    你是一个中医专家。以下是患者描述的通俗症状：
    [{symptoms_str}]
    
    由于之前的检索效果不佳，请将这些症状翻译或提炼为一个更为专业的中医检索词（例如将“肚子胀怕冷”重写为“脾胃虚寒 腹胀”）。
    请直接输出新的检索词（不同词之间用空格隔开），不要输出任何解释或其他内容。
    """

    llm = model_manager.get_model()
    try:
        response = llm.invoke([SystemMessage(content=prompt)])
        new_query = response.content.strip()
        # 强行覆盖当前的症状作为下一次搜索的依据（或者可以选择追加）
        new_symptoms = new_query.split()
    except Exception as e:
        print(f"❌ 重写节点调用异常: {e}")
        new_symptoms = symptoms

    print(f"📝 原始症状: {symptoms_str} -> 重写后: {' '.join(new_symptoms)}")
    return {"symptoms": new_symptoms}


def rag_decision_logic(state: AgentState):
    """
    RAG 路由决策逻辑。
    """
    # 只有当用户意图是诊疗且已经提取到症状时才尝试 RAG
    if state.get("intent_type") == "diagnose" and state.get("symptoms"):
        return "rag_search"
    return "diagnosis"


def rag_loop_logic(state: AgentState):
    """
    判断 RAG 是否需要重试或结束。
    """
    retry_count = state.get("rag_retry_count", 0)
    # The grader node returns new state values which are available in `state`
    score = state.get("rag_score", 1.0)

    print(f"🔍 路由条件诊断 | 当前得分: {score}, 当前重试次数: {retry_count}")

    if score >= config.RAG_SCORE_THRESHOLD or retry_count >= config.RAG_MAX_RETRIES:
        return "diagnosis"
    return "rag_rewrite"


# --- 独立测试块 ---
if __name__ == "__main__":
    # 模拟一个包含症状的 State
    test_state = {
        "symptoms": ["肚子胀", "怕冷", "舌苔白"],
        "messages": [],
        "intent_type": "diagnose"
    }
    print("🧪 正在进行 RAG 独立功能测试...")
    rag_search_node(test_state)
