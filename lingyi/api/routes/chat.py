"""聊天路由 - POST /api/chat（REST/SSE）+ WebSocket /api/ws/chat（流式）。"""

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from pydantic import BaseModel

from lingyi.agent.session_naming import DEFAULT_THREAD_TITLE
from lingyi.api.deps import decode_access_token, get_agent, get_current_user, get_storage
from lingyi.api.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# 仅推送 diagnosis/treatment/synthesis 节点的 LLM token（用户可见的理法方药）；
# 过滤 safety_guard/inquiry/rag_search/profile_writer 等内部 LLM 调用（返回 JSON/结构化输出，不应展示）。
# synthesis 用于多智能体模式（综合节点生成辨证+处方，等价于单 Agent 的 diagnosis+treatment）。
# SSE 与 WS 共用此过滤，避免 WS 泄漏内部 token 造成顺序错乱。
_STREAM_NODES = {"diagnosis", "treatment", "synthesis"}

# 单轮响应用时告警阈值（秒）
_SLOW_THRESHOLD = 30.0

# LangGraph 递归深度上限：多智能体会诊图含 synthesis<->reviewer/safety_check 重试循环，
# 默认 25 可能不够；设 50 留足余量（单次路径约 8 步，重试最多 3 轮）。
_RECURSION_LIMIT = 50


class MessageItem(BaseModel):
    """历史消息项（用于 /threads/{id}/messages 响应）。"""

    role: str
    content: str


def _extract_last_ai_response(messages: list[BaseMessage]) -> str:
    """
    从消息列表取最后一条 AI 消息内容。

    Agent 图可能在末尾追加非 AI 消息，因此遍历取最后一条 type=ai 的消息，
    而非直接取 messages[-1]。无 AI 消息时回退到最后一条。
    """
    for msg in reversed(messages):
        if getattr(msg, "type", "") in ("ai", "assistant") and getattr(msg, "content", ""):
            return msg.content
    return messages[-1].content if messages else ""


async def _session_rename_task(
    storage: Any,
    thread_id: str,
    username: str,
    first_message: str,
    diagnosis: str,
    llm: Any,
) -> None:
    """后台任务：先查当前标题，若为默认则生成并重命名（fire-and-forget）。"""
    try:
        # 异步查标题：避免覆盖用户手动重命名
        threads = await storage.get_threads(username)
        current_title = ""
        for t in threads:
            if getattr(t, "thread_id", "") == thread_id:
                current_title = getattr(t, "title", "") or ""
                break
        if current_title and current_title != DEFAULT_THREAD_TITLE:
            return  # 已有自定义标题，跳过

        from lingyi.agent.session_naming import generate_session_title

        title = await generate_session_title(llm, first_message, diagnosis)
        if title:
            await storage.rename_thread(thread_id, title, username)
            logger.info("会话已重命名: thread=%s title='%s'", thread_id, title)
    except Exception as e:  # noqa: BLE001 - 命名失败不影响主流程
        logger.warning("会话命名后台任务失败: %s", e)


def _maybe_schedule_session_rename(
    http_request: Request,
    storage: Any,
    thread_id: str,
    username: str,
    first_message: str,
    diagnosis: str,
) -> None:
    """会话命名：fire-and-forget 调度后台任务生成简短标题。

    复用 ProfileWriter 的 _pending 任务集合（防 GC、应用关闭时 flush）。
    命名是体验优化、非关键路径，任何异常静默跳过。
    """
    try:
        profile_writer = getattr(http_request.app.state, "profile_writer", None)
        llm = getattr(profile_writer, "llm", None)
        if llm is None:
            return
        import asyncio

        task = asyncio.create_task(
            _session_rename_task(storage, thread_id, username, first_message, diagnosis, llm)
        )
        pending = getattr(profile_writer, "_pending", None)
        if pending is not None:
            pending.add(task)
            task.add_done_callback(pending.discard)
    except Exception as e:  # noqa: BLE001 - 命名失败不影响主流程
        logger.warning("会话命名调度失败: %s", e)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    agent: Any = Depends(get_agent),
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
    stream: bool = False,
):
    """
    聊天端点 - 接收用户消息，调用 Agent 处理，返回回复。

    stream=true 时返回 SSE 流式响应，否则返回完整 JSON。

    SSE 事件契约（多智能体模式）:
      {token: "..."}                              - LLM token（diagnosis/treatment/synthesis 节点）
      {type:"stage",stage,label,status}           - 会诊阶段进度（自定义流）
      {done:true,thread_id,elapsed_ms,notes?}     - 完成（notes=会诊笔记，仅多智能体）
      {error:"..."}                               - 错误
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    await storage.add_thread(username, thread_id)

    state_input = {
        "messages": [HumanMessage(content=request.message)],
        "input_files": request.files,
        "thread_id": thread_id,
        "username": username,
        "intent_type": "chat",
    }
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": _RECURSION_LIMIT}

    # 流式模式 - 边收边发，前端实时显示
    if stream:
        import time

        async def event_generator():
            t_start = time.perf_counter()
            seq = 0
            try:
                # 多模式流：messages（LLM token）+ custom（阶段进度事件）
                # langgraph 1.2.6: 多模式时每个 chunk 为 (mode, data) 元组
                async for chunk in agent.astream(
                    state_input, config=config, stream_mode=["messages", "custom"]
                ):
                    mode, data = chunk
                    if mode == "custom":
                        # 自定义流事件：阶段进度（由 graph_multiagent 节点通过 get_stream_writer 发送）
                        if isinstance(data, dict) and data.get("type") == "stage":
                            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                        continue
                    # messages 模式: data = (msg_chunk, metadata)
                    if not isinstance(data, tuple) or len(data) < 2:
                        continue
                    msg, metadata = data[0], data[1]
                    node = metadata.get("langgraph_node", "") if isinstance(metadata, dict) else ""
                    step = metadata.get("langgraph_step", "") if isinstance(metadata, dict) else ""
                    if node not in _STREAM_NODES:
                        continue
                    if isinstance(msg, AIMessageChunk) and msg.content:
                        seq += 1
                        logger.debug(
                            "SSE token: node=%s step=%s seq=%d len=%d", node, step, seq, len(msg.content)
                        )
                        yield f"data: {json.dumps({'token': msg.content}, ensure_ascii=False)}\n\n"
                elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                if elapsed_ms > _SLOW_THRESHOLD * 1000:
                    logger.warning("慢响应: thread=%s elapsed=%dms", thread_id, elapsed_ms)
                else:
                    logger.info("流式完成: thread=%s elapsed=%dms", thread_id, elapsed_ms)

                # 读取最终状态，提取会诊笔记（多智能体）供前端折叠展示
                notes = []
                diagnosis = ""
                try:
                    snapshot = await agent.aget_state(config)
                    if snapshot and snapshot.values:
                        notes = snapshot.values.get("consultation_notes", []) or []
                        diagnosis = snapshot.values.get("diagnosis", "") or ""
                except Exception as e:  # noqa: BLE001
                    logger.warning("读取最终状态失败: %s", e)

                yield f"data: {json.dumps({'done': True, 'thread_id': thread_id, 'elapsed_ms': elapsed_ms, 'notes': notes, 'diagnosis': diagnosis}, ensure_ascii=False)}\n\n"

                # 会话命名：首条消息后异步生成标题（fire-and-forget，不阻塞响应）
                _maybe_schedule_session_rename(http_request, storage, thread_id, username, request.message, diagnosis)
            except Exception as e:
                logger.error("流式聊天失败: %s", e, exc_info=True)
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # 非流式模式
    try:
        result = await agent.ainvoke(state_input, config=config)
    except Exception as e:
        logger.error("Agent 调用失败: %s", e, exc_info=True)
        return ChatResponse(response=f"抱歉，处理过程中出现错误: {e}", thread_id=thread_id)

    response_text = _extract_last_ai_response(result.get("messages", []))
    logger.info("Agent 回复: len=%d, thread=%s", len(response_text), thread_id)

    # 会话命名：首条消息后异步生成标题（fire-and-forget，不阻塞响应）
    diagnosis = result.get("diagnosis", "") or ""
    _maybe_schedule_session_rename(http_request, storage, thread_id, username, request.message, diagnosis)

    return ChatResponse(
        response=response_text,
        thread_id=thread_id,
        intent_type=result.get("intent_type", "chat"),
        symptoms=result.get("symptoms", []),
    )


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket 聊天端点 - 使用 graph.astream 流式推送 token。

    遵循 LangGraph 流式接口（stream_mode="messages"），不使用 ainvoke 阻塞等待。
    鉴权：通过 query 参数 ?token=<JWT> 传入，复用 decode_access_token 校验，
    拒绝匿名连接（不再使用 default_user）。
    """
    # WS 无法直接用 Depends，从 query 参数取 token 并校验
    token = websocket.query_params.get("token")
    try:
        username = decode_access_token(token)
    except HTTPException:
        await websocket.close(code=4401, reason="未认证或 token 无效")
        return

    await websocket.accept()
    logger.info("WebSocket 连接建立: user=%s", username)

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            thread_id = data.get("thread_id", str(uuid.uuid4()))

            if not message:
                continue

            # 从 app.state 读取实例
            agent = websocket.app.state.agent
            storage = websocket.app.state.storage
            if agent is None:
                await websocket.send_json({"type": "error", "message": "Agent 未初始化"})
                continue

            await storage.add_thread(username, thread_id)
            state_input = {
                "messages": [HumanMessage(content=message)],
                "thread_id": thread_id,
                "username": username,
                "intent_type": "chat",
            }
            config = {"configurable": {"thread_id": thread_id}, "recursion_limit": _RECURSION_LIMIT}

            try:
                import time

                t_start = time.perf_counter()
                logger.info(
                    "Agent 流式处理: %s (thread=%s, user=%s)", message[:30], thread_id, username
                )
                async for chunk in agent.astream(
                    state_input, config=config, stream_mode=["messages", "custom"]
                ):
                    mode, data = chunk
                    if mode == "custom":
                        if isinstance(data, dict) and data.get("type") == "stage":
                            await websocket.send_json(data)
                        continue
                    if not isinstance(data, tuple) or len(data) < 2:
                        continue
                    msg, meta = data[0], data[1]
                    node = meta.get("langgraph_node", "") if isinstance(meta, dict) else ""
                    if node not in _STREAM_NODES:
                        continue
                    if isinstance(msg, AIMessageChunk) and msg.content:
                        await websocket.send_json({"type": "token", "content": msg.content})
                elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                # 读取会诊笔记（多智能体）随 done 下发
                notes = []
                try:
                    snap = await agent.aget_state(config)
                    if snap and snap.values:
                        notes = snap.values.get("consultation_notes", []) or []
                except Exception:  # noqa: BLE001
                    pass
                await websocket.send_json(
                    {"type": "done", "thread_id": thread_id, "elapsed_ms": elapsed_ms, "notes": notes}
                )
                logger.info("Agent 流式完成: thread=%s elapsed=%dms", thread_id, elapsed_ms)
            except Exception as e:
                logger.error("Agent 流式失败: %s", e, exc_info=True)
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开: user=%s", username)


@router.get("/threads/{thread_id}/messages", response_model=list[MessageItem])
async def get_thread_messages(thread_id: str, agent: Any = Depends(get_agent)):
    """
    获取指定会话的消息历史 - 通过公开 API agent.aget_state 读取。

    不再深入 checkpointer 内部结构（channel_values），使用 LangGraph 公开 StateSnapshot。
    """
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = await agent.aget_state(config)
        messages = snapshot.values.get("messages", []) if snapshot else []
        result: list[MessageItem] = []
        for msg in messages:
            if isinstance(msg, HumanMessage) and msg.content:
                result.append(MessageItem(role="user", content=msg.content))
            elif isinstance(msg, AIMessage) and msg.content:
                result.append(MessageItem(role="assistant", content=msg.content))
        return result
    except Exception as e:
        logger.warning("获取消息历史失败: thread_id=%s, error=%s", thread_id, e)
        return []
