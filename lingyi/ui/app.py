"""
Streamlit 主入口 — 组装认证、对话、侧边栏模块。

启动方式: streamlit run lingyi/ui/app.py
"""

import streamlit as st

# 页面配置
st.set_page_config(
    page_title="灵医 - 中医诊疗智能体",
    page_icon="🎋",
    layout="wide",
)

# 初始化 session state
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = ""
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "token" not in st.session_state:
    st.session_state["token"] = ""

# API 地址
API_BASE = "http://localhost:8000"

# ==================== 主界面 ====================

st.title("🎋 灵医 — 中医诊疗智能体")
st.caption("基于 LangGraph 的多智能体中医诊疗系统")

# 认证检查
from lingyi.ui.auth import render_auth_form

username = render_auth_form(API_BASE)

if username:
    # 渲染侧边栏
    from lingyi.ui.sidebar import render_sidebar
    render_sidebar(API_BASE)

    # 渲染对话区
    from lingyi.ui.chat import render_chat
    render_chat(API_BASE)
else:
    st.info("请先登录或注册以开始使用。")
    st.markdown("---")
    st.markdown("""
    ### 关于灵医

    灵医是一款基于 **LangGraph** 框架和 **Qwen3** 大模型驱动的中医诊疗多智能体系统。

    **核心功能:**
    - 🩺 多轮问诊交互，逐步收集症状
    - 📚 按需 RAG 知识检索（中医古籍）
    - 💊 辨证论治与处方建议
    - 🛡️ 双重安全护栏（十八反/十九畏）
    - 💾 患者画像持久化

    ⚠️ **免责声明**: 本系统仅供技术探索和学术研究，不具备临床执业资格。
    """)
