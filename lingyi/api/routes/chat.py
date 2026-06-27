"""聊天路由 — POST /api/chat + WebSocket /api/ws/chat。"""

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from lingyi.api.deps import get_agent, get_storage
from lingyi.api.schemas import ChatRequest, ChatResponse
from lingyi.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    聊天端点 — 接收用户消息，调用 Agent 处理，返回回复。
    """
    from langchain_core.messages import HumanMessage

    settings = get_settings()
    agent = get_agent(settings)
    storage = get_storage(settings)

    thread_id = request.thread_id or str(uuid.uuid4())
    await storage.add_thread("default_user", thread_id)

    state_input = {
        "messages": [HumanMessage(content=request.message)],
        "input_files": request.files,
        "thread_id": thread_id,
        "intent_type": "chat",  # 重置意图，防止 checkpointer 中的旧值影响路由
    }

    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = await agent.ainvoke(state_input, config=config)
    except Exception as e:
        logger.error("Agent 调用失败: %s", e, exc_info=True)
        return ChatResponse(response=f"抱歉，处理过程中出现错误: {e}", thread_id=thread_id)

    messages = result.get("messages", [])
    # 从消息列表中取最后一条 AI 回复（跳过用户消息）
    response_text = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") in ("ai", "assistant"):
            response_text = getattr(msg, "content", "")
            break
    if not response_text and messages:
        response_text = getattr(messages[-1], "content", "")
    logger.info("Agent 回复: type=%s len=%d", getattr(messages[-1], "type", "?") if messages else "N/A", len(response_text))

    return ChatResponse(
        response=response_text,
        thread_id=thread_id,
        intent_type=result.get("intent_type", "chat"),
        symptoms=result.get("symptoms", []),
    )


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket 聊天端点 — 调用 Agent 处理消息并返回回复。

    使用 ainvoke 等待完整结果后一次性返回。
    后续可优化为 astream 流式输出。
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

            from langchain_core.messages import HumanMessage

            settings = get_settings()
            agent = get_agent(settings)
            storage = get_storage(settings)
            await storage.add_thread("default_user", thread_id)

            state_input = {
                "messages": [HumanMessage(content=message)],
                "thread_id": thread_id,
            }

            config = {"configurable": {"thread_id": thread_id}}

            try:
                logger.info("Agent 开始处理: %s (thread=%s)", message[:30], thread_id)
                result = await agent.ainvoke(state_input, config=config)
                messages = result.get("messages", [])
                response_text = getattr(messages[-1], "content", "") if messages else ""

                await websocket.send_json({
                    "type": "final",
                    "response": response_text,
                    "thread_id": thread_id,
                })
                logger.info("Agent 处理完成: %d 字符", len(response_text))
            except Exception as e:
                logger.error("Agent 执行失败: %s", e, exc_info=True)
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开")
