"""
Streamlit 认证模块 — 登录/注册表单。

通过 HTTP 调用 FastAPI 后端的认证接口。
使用 JWT Token 做 API 认证，Cookie 做 UI 层免登。
"""

import streamlit as st
import httpx


def render_auth_form(api_base: str = "http://localhost:8000") -> str | None:
    """
    渲染登录/注册表单。

    Args:
        api_base: FastAPI 后端地址

    Returns:
        登录成功返回 username，未登录返回 None
    """
    if st.session_state.get("username"):
        return st.session_state["username"]

    st.markdown("### 🔐 登录 / 注册")

    tab_login, tab_register = st.tabs(["登录", "注册"])

    with tab_login:
        username = st.text_input("用户名", key="login_username")
        password = st.text_input("密码", type="password", key="login_password")

        if st.button("登录", key="login_btn"):
            if username and password:
                try:
                    resp = httpx.post(
                        f"{api_base}/api/login",
                        json={"username": username, "password": password},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        st.session_state["username"] = username
                        st.session_state["token"] = data.get("access_token", "")
                        st.rerun()
                    else:
                        st.error("用户名或密码错误")
                except httpx.ConnectError:
                    st.error("无法连接到后端服务，请确认 API 已启动")
                except Exception as e:
                    st.error(f"登录失败: {e}")

    with tab_register:
        new_username = st.text_input("用户名", key="reg_username")
        new_password = st.text_input("密码", type="password", key="reg_password")
        confirm_password = st.text_input("确认密码", type="password", key="reg_confirm")

        if st.button("注册", key="reg_btn"):
            if not new_username or not new_password:
                st.error("请填写用户名和密码")
            elif new_password != confirm_password:
                st.error("两次密码不一致")
            elif len(new_password) < 6:
                st.error("密码至少 6 位")
            else:
                try:
                    resp = httpx.post(
                        f"{api_base}/api/register",
                        json={"username": new_username, "password": new_password},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        st.success("注册成功，请登录")
                    else:
                        st.error("注册失败，用户名可能已存在")
                except httpx.ConnectError:
                    st.error("无法连接到后端服务")
                except Exception as e:
                    st.error(f"注册失败: {e}")

    return None


def logout():
    """清除登录状态。"""
    st.session_state.pop("username", None)
    st.session_state.pop("token", None)
