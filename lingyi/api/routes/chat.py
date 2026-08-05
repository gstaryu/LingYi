"""聊天路由 - POST /api/chat（REST/SSE）+ WebSocket /api/ws/chat（流式）。"""

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from pydantic import BaseModel

from lingyi.api.deps import decode_access_token, get_agent, get_current_user, get_storage
from lingyi.api.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# 仅推送 diagnosis/treatment 节点的 LLM token（用户可见的理法方药）；
# 过滤 safety_guard/inquiry/rag_search/profile_writer 等内部 LLM 调用（返回 JSON/结构化输出，不应展示）。
# SSE 与 WS 共用此过滤，避免 WS 泄漏内部 token 造成顺序错乱。
_STREAM_NODES = {"diagnosis", "treatment"}

# 单轮响应用时告警阈值（秒）
_SLOW_THRESHOLD = 30.0


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


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent: Any = Depends(get_agent),
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
    stream: bool = False,
):
    """
    聊天端点 - 接收用户消息，调用 Agent 处理，返回回复。

    stream=true 时返回 SSE 流式响应，否则返回完整 JSON。
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
    config = {"configurable": {"thread_id": thread_id}}

    # 流式模式 - 边收边发，前端实时显示
    if stream:
        import time

        async def event_generator():
            t_start = time.perf_counter()
            seq = 0
            try:
                async for chunk in agent.astream(state_input, config=config, stream_mode="messages"):
                    msg, metadata = chunk
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
                yield f"data: {json.dumps({'done': True, 'thread_id': thread_id, 'elapsed_ms': elapsed_ms}, ensure_ascii=False)}\n\n"
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
            config = {"configurable": {"thread_id": thread_id}}

            try:
                import time

                t_start = time.perf_counter()
                logger.info(
                    "Agent 流式处理: %s (thread=%s, user=%s)", message[:30], thread_id, username
                )
                async for chunk in agent.astream(
                    state_input, config=config, stream_mode="messages"
                ):
                    msg, meta = chunk
                    node = meta.get("langgraph_node", "") if isinstance(meta, dict) else ""
                    if node not in _STREAM_NODES:
                        continue
                    if isinstance(msg, AIMessageChunk) and msg.content:
                        await websocket.send_json({"type": "token", "content": msg.content})
                elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                await websocket.send_json(
                    {"type": "done", "thread_id": thread_id, "elapsed_ms": elapsed_ms}
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
