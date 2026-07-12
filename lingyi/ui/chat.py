"""
Streamlit 对话模块 — 对话渲染和消息输入。

通过 HTTP 调用 FastAPI 后端的 /api/chat 接口。
"""

import streamlit as st
import httpx


def render_chat(api_base: str = "http://localhost:8000"):
    """
    渲染对话区。

    Args:
        api_base: FastAPI 后端地址
    """
    # 显示历史消息
    for msg in st.session_state.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        with st.chat_message(role):
            st.markdown(content)

    # 用户输入
    if prompt := st.chat_input("请描述您的症状..."):
        # 显示用户消息
        st.session_state.setdefault("messages", []).append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 调用 API
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                response = _call_chat_api(api_base, prompt)
                st.markdown(response)
                st.session_state["messages"].append({"role": "assistant", "content": response})


def _call_chat_api(api_base: str, message: str) -> str:
    """
    调用 FastAPI 聊天接口（HTTP POST 回退）。

    Args:
        api_base: FastAPI 后端地址
        message: 用户消息

    Returns:
        AI 回复内容
    """
    thread_id = st.session_state.get("thread_id", "")

    try:
        resp = httpx.post(
            f"{api_base}/api/chat",
            json={
                "message": message,
                "thread_id": thread_id,
            },
            headers=_get_auth_headers(),
            timeout=300,
        )

        if resp.status_code == 200:
            data = resp.json()
            new_thread_id = data.get("thread_id", "")
            if new_thread_id and new_thread_id != thread_id:
                st.session_state["thread_id"] = new_thread_id
            return data.get("response", "抱歉，未能获取回复。")
        else:
            return f"API 错误: {resp.status_code}"

    except httpx.ConnectError:
        return "⚠️ 无法连接到后端服务。请确认 FastAPI 已启动: `uvicorn lingyi.api.app:app`"
    except httpx.ReadTimeout:
        return "⚠️ 请求超时，Agent 处理时间过长。请稍后重试。"
    except Exception as e:
        return f"⚠️ 请求失败: {e}"


def _get_auth_headers() -> dict:
    """获取认证头。"""
    token = st.session_state.get("token", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def clear_chat():
    """清空当前对话。"""
    st.session_state["messages"] = []
    st.session_state["thread_id"] = ""
