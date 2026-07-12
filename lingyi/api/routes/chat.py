"""聊天路由 - POST /api/chat（REST/SSE）+ WebSocket /api/ws/chat（流式）。"""

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from pydantic import BaseModel

from lingyi.api.deps import get_agent, get_current_user, get_storage
from lingyi.api.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter()


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
        # 仅推送 diagnosis/treatment 节点的 LLM token（用户可见的理法方药）；
        # 过滤掉 safety_guard/inquiry/profile_writer 等内部 LLM 调用（返回 JSON/结构化输出，不应展示）
        _STREAM_NODES = {"diagnosis", "treatment"}

        async def event_generator():
            try:
                async for chunk in agent.astream(state_input, config=config, stream_mode="messages"):
                    msg, metadata = chunk
                    node = metadata.get("langgraph_node", "") if isinstance(metadata, dict) else ""
                    if node not in _STREAM_NODES:
                        continue
                    if isinstance(msg, AIMessageChunk) and msg.content:
                        yield f"data: {json.dumps({'token': msg.content}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'done': True, 'thread_id': thread_id}, ensure_ascii=False)}\n\n"
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
    WS 鉴权（query token）为后续增强；当前以 default_user 记录线程归属。
    """
    await websocket.accept()
    logger.info("WebSocket 连接建立")

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            thread_id = data.get("thread_id", str(uuid.uuid4()))

            if not message:
                continue

            # WS 无法直接用 Depends，从 app.state 读取实例
            agent = websocket.app.state.agent
            storage = websocket.app.state.storage
            if agent is None:
                await websocket.send_json({"type": "error", "message": "Agent 未初始化"})
                continue

            await storage.add_thread("default_user", thread_id)
            state_input = {
                "messages": [HumanMessage(content=message)],
                "thread_id": thread_id,
                "username": "default_user",
                "intent_type": "chat",
            }
            config = {"configurable": {"thread_id": thread_id}}

            try:
                logger.info("Agent 流式处理: %s (thread=%s)", message[:30], thread_id)
                async for chunk in agent.astream(state_input, config=config, stream_mode="messages"):
                    msg, _meta = chunk
                    if isinstance(msg, AIMessageChunk) and msg.content:
                        await websocket.send_json({"type": "token", "content": msg.content})
                await websocket.send_json({"type": "done", "thread_id": thread_id})
                logger.info("Agent 流式完成: thread=%s", thread_id)
            except Exception as e:
                logger.error("Agent 流式失败: %s", e, exc_info=True)
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开")


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
