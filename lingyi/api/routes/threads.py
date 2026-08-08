"""线程管理路由 - CRUD /api/threads（按认证用户隔离）。"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from lingyi.api.deps import get_current_user, get_storage
from lingyi.api.schemas import ThreadCreate, ThreadRename, ThreadResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/threads", response_model=list[ThreadResponse])
async def list_threads(
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """获取当前认证用户的所有会话线程。"""
    threads = await storage.get_threads(username)
    return [
        ThreadResponse(thread_id=t.thread_id, title=t.title, created_at=t.created_at)
        for t in threads
    ]


@router.post("/threads", response_model=ThreadResponse)
async def create_thread(
    request: ThreadCreate,
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """创建新会话线程，归属当前认证用户。"""
    thread_id = str(uuid.uuid4())
    await storage.add_thread(username, thread_id)
    return ThreadResponse(thread_id=thread_id, title=request.title, created_at="")


@router.put("/threads/{thread_id}")
async def rename_thread(
    thread_id: str,
    request: ThreadRename,
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """重命名会话线程（仅限归属用户）。"""
    updated = await storage.rename_thread(thread_id, request.new_title, username)
    if not updated:
        raise HTTPException(status_code=404, detail="线程不存在或不归属当前用户")
    return {"status": "ok"}


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """删除会话线程（仅限归属用户）。"""
    deleted = await storage.delete_thread(thread_id, username)
    if not deleted:
        raise HTTPException(status_code=404, detail="线程不存在或不归属当前用户")
    return {"status": "ok"}
