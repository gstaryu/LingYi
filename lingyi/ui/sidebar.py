"""
Streamlit 侧边栏模块 — 线程管理和用户画像展示。

通过 HTTP 调用 FastAPI 后端的 /api/threads 和 /api/profiles 接口。
"""

import streamlit as st
import httpx


def render_sidebar(api_base: str = "http://localhost:8000"):
    """渲染侧边栏。"""
    with st.sidebar:
        username = st.session_state.get("username", "未登录")
        st.markdown(f"**👤 {username}**")

        if st.button("退出登录"):
            from lingyi.ui.auth import logout
            logout()
            st.rerun()

        st.divider()

        if st.button("➕ 新建对话", use_container_width=True):
            from lingyi.ui.chat import clear_chat
            clear_chat()
            st.rerun()

        st.markdown("### 📋 历史对话")

        threads = _get_threads(api_base)
        current_thread = st.session_state.get("thread_id", "")

        for thread in threads:
            tid = thread.get("thread_id", "")
            title = thread.get("title", "新对话")
            is_current = tid == current_thread

            col1, col2 = st.columns([4, 1])
            with col1:
                label = f"{'▶ ' if is_current else ''}{title}"
                if st.button(label, key=f"thread_{tid}", use_container_width=True):
                    st.session_state["thread_id"] = tid
                    st.session_state["messages"] = []
                    st.rerun()
            with col2:
                if st.button("🗑", key=f"del_{tid}"):
                    _delete_thread(api_base, tid)
                    if current_thread == tid:
                        from lingyi.ui.chat import clear_chat
                        clear_chat()
                    st.rerun()

        st.divider()

        st.markdown("### 🩺 患者画像")
        profile = _get_profile(api_base, username)
        if profile:
            st.markdown(f"**体质:** {profile.get('constitution', '未知')}")
            st.markdown(f"**过敏史:** {profile.get('allergies', '无')}")
            history = profile.get("past_history", [])
            if history:
                st.markdown("**既往史:**")
                for h in history[-3:]:
                    st.markdown(f"- {h}")


def _get_threads(api_base: str) -> list:
    """获取线程列表。"""
    try:
        resp = httpx.get(f"{api_base}/api/threads", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def _delete_thread(api_base: str, thread_id: str):
    """删除线程。"""
    try:
        httpx.delete(f"{api_base}/api/threads/{thread_id}", timeout=10)
    except Exception:
        pass


def _get_profile(api_base: str, patient_id: str) -> dict:
    """获取患者画像。"""
    try:
        resp = httpx.get(f"{api_base}/api/profiles/{patient_id}", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}
