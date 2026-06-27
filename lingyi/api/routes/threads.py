"""线程管理路由 — CRUD /api/threads。"""

import logging
import uuid

from fastapi import APIRouter

from lingyi.api.deps import get_storage
from lingyi.api.schemas import ThreadCreate, ThreadRename, ThreadResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/threads", response_model=list[ThreadResponse])
async def list_threads(username: str = "default_user"):
    """获取用户的所有会话线程。"""
    storage = get_storage()
    threads = await storage.get_threads(username)
    return [
        ThreadResponse(thread_id=t.thread_id, title=t.title, created_at=t.created_at)
        for t in threads
    ]


@router.post("/threads", response_model=ThreadResponse)
async def create_thread(request: ThreadCreate, username: str = "default_user"):
    """创建新会话线程。"""
    storage = get_storage()
    thread_id = str(uuid.uuid4())
    await storage.add_thread(username, thread_id)
    return ThreadResponse(thread_id=thread_id, title=request.title, created_at="")


@router.put("/threads/{thread_id}")
async def rename_thread(thread_id: str, request: ThreadRename):
    """重命名会话线程。"""
    storage = get_storage()
    await storage.rename_thread(thread_id, request.new_title)
    return {"status": "ok"}


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str):
    """删除会话线程。"""
    storage = get_storage()
    await storage.delete_thread(thread_id)
    return {"status": "ok"}
