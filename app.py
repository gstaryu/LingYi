import streamlit as st
import uuid
import os
import extra_streamlit_components as stx
from langchain_core.messages import HumanMessage, AIMessage
from agent.graph import app as agent_app
from config import config
from storage.profile_manager import ProfileManager

st.set_page_config(page_title="灵医 - 中医智能体", page_icon="🎋", layout="wide")

# 初始化 session state
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "username" not in st.session_state:
    st.session_state.username = None

if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = "login"

def get_cookie_manager():
    return stx.CookieManager()

def login_form(cookie_manager):
    # 使用自定义样式让登录框更美观居中
    st.markdown("""
        <style>
        .block-container {
            max-width: 600px;
            padding-top: 10vh;
        }
        .auth-title {
            text-align: center;
            font-size: 3rem !important;
            font-weight: 700;
            color: #2E7D32;
            margin-bottom: 0.5rem;
        }
        .auth-subtitle {
            text-align: center;
            color: #666;
            font-size: 1.1rem;
            margin-bottom: 2rem;
        }
        .stTabs [data-baseweb="tab-list"] {
            justify-content: center;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='auth-title'>🎋 灵医</div>", unsafe_allow_html=True)
    st.markdown("<div class='auth-subtitle'>欢迎使用您的专属中医健康信息助手</div>", unsafe_allow_html=True)

    pm = ProfileManager()

    # 使用 st.tabs 替代原本的按钮切换模式，界面更现代、丝滑
    tab_login, tab_register = st.tabs(["🔐 账号登录", "📝 新用户注册"])

    with tab_login:
        with st.form("login_form", border=True):
            username = st.text_input("用户名", max_chars=20, placeholder="请输入用户名")
            password = st.text_input("密码", type="password", max_chars=30, placeholder="请输入密码")
            submitted = st.form_submit_button("登 录", type="primary", use_container_width=True)

            if submitted:
                if not username.strip() or not password.strip():
                    st.error("用户名和密码不能为空！")
                else:
                    if pm.verify_user(username.strip(), password.strip()):
                        st.session_state.username = username.strip()
                        # 写入 cookie，有效期 7 天
                        cookie_manager.set("ly_user", st.session_state.username, key="set_ly_user", expires_at=None, max_age=7*24*3600)
                        pm.add_thread(st.session_state.username, st.session_state.thread_id)
                        st.rerun()
                    else:
                        st.error("用户名或密码错误！")

    with tab_register:
        with st.form("register_form", border=True):
            username = st.text_input("设定用户名", max_chars=20, placeholder="起一个好记的用户名")
            password = st.text_input("设定密码", type="password", max_chars=30, placeholder="至少6位数字或字母")
            password_confirm = st.text_input("确认密码", type="password", max_chars=30, placeholder="请再次输入密码")
            submitted = st.form_submit_button("建档注册", type="primary", use_container_width=True)

            if submitted:
                if not username.strip():
                    st.error("用户名不能为空！")
                elif password != password_confirm:
                    st.error("两次输入的密码不一致，请重试！")
                elif len(password.strip()) < 6:
                    st.error("密码长度必须不少于6位！")
                else:
                    # 尝试创建
                    success = pm.create_user(username.strip(), password.strip())
                    if success:
                        st.success("建档成功！正在为您安排专属诊室...")
                        st.session_state.username = username.strip()
                        # 写入 cookie，有效期 7 天
                        cookie_manager.set("ly_user", st.session_state.username, key="set_reg_ly_user", expires_at=None, max_age=7*24*3600)
                        pm.add_thread(st.session_state.username, st.session_state.thread_id)
                        import time
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("该用户名已被占用，请换一个重试！")


def main():
    cookie_manager = get_cookie_manager()

    # 等待 Cookie 管理器初始化完成（防止页面刷新时闪过登录页）
    cookies = cookie_manager.get_all()
    if not isinstance(cookies, dict):
        return

    # 尝试从 cookie 恢复会话
    if not st.session_state.username and not st.session_state.get("logout_triggered", False):
        ly_user = cookie_manager.get(cookie="ly_user")
        if ly_user:
            st.session_state.username = ly_user

    # 还未登录则显示登录界面
    if not st.session_state.username:
        login_form(cookie_manager)
        return

    # 从 URL 恢复 thread_id
    query_params = st.query_params
    if "thread_id" in query_params:
        # 只有当新打开或者刷新时，应用 URL 里的参数
        if st.session_state.thread_id != query_params["thread_id"]:
            st.session_state.thread_id = query_params["thread_id"]
            st.session_state.messages = []
            try:
                config_dict = {"configurable": {"thread_id": st.session_state.thread_id}}
                state_snap = agent_app.get_state(config_dict)
                if state_snap and state_snap.values:
                    st.session_state.messages = state_snap.values.get("messages", [])
            except Exception:
                pass
    else:
        # 如果 URL 没有，更新 URL
        st.query_params.thread_id = st.session_state.thread_id

    st.title("🎋 灵医 (LingYi)")
    st.markdown("<span style='color:gray; font-size:small'>*中医多智能体健康信息助手*</span>", unsafe_allow_html=True)

    # 实例化 Profile Manager
    pm = ProfileManager()

    # 侧边栏：多线程管理、画像与文件上传
    with st.sidebar:
        st.header(f"👋 欢迎, {st.session_state.username}")
        if st.button("🚪 退出登录"):
            st.session_state.username = None
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.query_params.clear()
            cookie_manager.delete("ly_user", key="del_ly_user")
            st.session_state.logout_triggered = True
            st.rerun()

        st.divider()

        st.header("🗂️ 对话记录")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("➕ 新建对话"):
                # 如果当前就对话记录没有任何消息，就不必新建了
                if st.session_state.messages:
                    st.session_state.thread_id = str(uuid.uuid4())
                    st.session_state.messages = []
                    st.query_params.thread_id = st.session_state.thread_id
                    st.rerun()
                else:
                    st.toast("当前已经是新对话了", icon="ℹ️")

        # 只加载属于当前用户的历史记录供选择
        user_threads = pm.get_threads(st.session_state.username)
        history_opts = []
        history_map = {}

        # 将当前 session state 的 thread_id 确保在列表中显示最新
        current_id = st.session_state.thread_id

        for t in user_threads:
            display_title = t['title'] if t.get('title') else f"对话 {t['thread_id'][:8]}"
            label = f"{display_title} ({t['created_at'][:16]})"
            history_opts.append(label)
            history_map[label] = t['thread_id']

        # 如果当前是一个还没存进DB里的新记录，且用户有消息，或纯新界面，则补进去
        if not any(t['thread_id'] == current_id for t in user_threads):
            new_label = f"新对话 {current_id[:8]} (当前)"
            history_opts.insert(0, new_label)
            history_map[new_label] = current_id

        # 根据当前 thread_id 找寻默认 index
        default_idx = 0
        for i, opt in enumerate(history_opts):
            if history_map[opt] == current_id:
                default_idx = i
                break

        # 如果当前由于选择切换了线程，需要重载界面
        selected_opt = st.selectbox("切换历史对话记录", history_opts, index=default_idx)
        if selected_opt:
            target_id = history_map[selected_opt]
            if st.session_state.thread_id != target_id:
                st.session_state.thread_id = target_id
                st.query_params.thread_id = target_id
                # 重新从 LangGraph 状态提取所有历史 messages
                # 初始化空，等下如果LangGraph有记忆，可以考虑进一步还原界面。这里先保持前端空列表或依靠 RAG 后端。
                st.session_state.messages = []

                # 尝试从 LangGraph DB 恢复前端消息
                try:
                    config_dict = {"configurable": {"thread_id": target_id}}
                    state_snap = agent_app.get_state(config_dict)
                    if state_snap and state_snap.values:
                        recent_msgs = state_snap.values.get("messages", [])
                        st.session_state.messages = recent_msgs
                except Exception as e:
                    pass
                st.rerun()

        # 重命名功能
        if any(t['thread_id'] == current_id for t in user_threads):
            with st.expander("✏️ 重命名当前对话"):
                new_title = st.text_input("新名称", max_chars=30)
                if st.button("确认重命名"):
                    if new_title.strip():
                        pm.rename_thread(current_id, new_title.strip())
                        st.success("重命名成功！")
                        st.rerun()
                    else:
                        st.error("名称不能为空！")

            with st.expander("🗑️ 删除当前对话"):
                st.warning("删除后无法恢复，确定要删除吗？")
                if st.button("确认删除", type="primary"):
                    pm.delete_thread(current_id)
                    st.session_state.thread_id = str(uuid.uuid4())
                    st.session_state.messages = []
                    st.query_params.thread_id = st.session_state.thread_id
                    st.success("对话已删除！")
                    st.rerun()

        st.divider()

        st.header("👤 用户信息与资料")
        st.info(f"当前对话 ID: `{st.session_state.thread_id[:8]}`")

        # 获取刷新后的画像
        profile_data = pm.get_profile(st.session_state.thread_id)

        # 允许多种文件格式，并监听变化
        uploaded_files = st.file_uploader("上传您的检查报告或既往处方 (PDF/Word/TXT)", accept_multiple_files=True, type=["pdf", "doc", "docx", "txt"])

        st.divider()
        st.header("📋 长期画像 (Profile)")
        st.write(f"**体质**: {profile_data.get('constitution', '未知')}")
        st.write(f"**过敏史**: {profile_data.get('allergies', '无')}")

        past_history = profile_data.get("past_history", [])
        if past_history:
            with st.expander("既往诊疗记录"):
                for record in past_history:
                    st.caption(f"- {record}")
        else:
            st.write("**既往诊疗记录**: 暂无")

    # 渲染历史对话
    DISCLAIMER_HTML = "\n\n<span style='color:gray; font-size:small'>*本回答由 AI 生成，内容仅供参考，请仔细甄别。*</span>"

    for msg in st.session_state.messages:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        # 在渲染时为助手消息补上免责声明（如果后端未保存该免责声明）
        content = msg.content if hasattr(msg, 'content') else str(msg)
        if role == "assistant" and "本回答由 AI 生成" not in content:
            content = content + DISCLAIMER_HTML

        with st.chat_message(role):
            st.markdown(content, unsafe_allow_html=True)

    # 聊天输入
    if prompt := st.chat_input("请描述您的症状..."):
        # UI 显示用户的消息
        with st.chat_message("user"):
            st.markdown(prompt)

        human_msg = HumanMessage(content=prompt)
        st.session_state.messages.append(human_msg)

        # 用户发送消息时才真正保存 thread 到数据库
        pm.add_thread(st.session_state.username, st.session_state.thread_id)

        # 处理上传的文件并获取路径
        saved_file_paths = []
        if uploaded_files:
            upload_dir = os.path.join(config.STORAGE_DIR, "temp_uploads")
            os.makedirs(upload_dir, exist_ok=True)
            for uploaded_file in uploaded_files:
                if hasattr(uploaded_file, "name") and hasattr(uploaded_file, "getbuffer"):
                    file_path = os.path.join(upload_dir, uploaded_file.name)
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    saved_file_paths.append(file_path)

        # 准备传入 Graph 的初始状态
        state_input = {
            "messages": [human_msg],
            "input_files": saved_file_paths  # 传入文件列表供 Reader Node 消费
        }

        # 调用 Agent
        with st.chat_message("assistant"):
            with st.spinner("灵医正在思考..."):
                try:
                    # 使用配置传入 thread_id 保证记忆持久化
                    config_dict = {"configurable": {"thread_id": st.session_state.thread_id}}

                    # 获取图的最终执行结果 (此为非流式，如果需要流式可以后续改造)
                    result_state = agent_app.invoke(state_input, config=config_dict)

                    # 假定图的 messages 最后一个是 AI 返回的内容
                    final_messages = result_state.get("messages", [])
                    if final_messages:
                        ai_response = final_messages[-1].content

                        # 附加全局免责声明
                        disclaimer = "\n\n<span style='color:gray; font-size:small'>*本回答由 AI 生成，内容仅供参考，请仔细甄别。*</span>"
                        ai_response += disclaimer

                        st.markdown(ai_response, unsafe_allow_html=True)
                        st.session_state.messages.append(AIMessage(content=ai_response))

                    # 每次对话结束后，为了让左边栏画像立即更新，我们强制重启一次页面
                    st.rerun()
                except Exception as e:
                    st.error(f"处理发生异常: {e}")

if __name__ == "__main__":
    main()
