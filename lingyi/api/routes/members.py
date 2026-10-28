"""咨询人管理路由 - CRUD /api/members（按认证账号隔离）。

咨询人是账号下的就诊对象（本人 / 家庭成员）。主成员的 member_id 等于 username，
保证多成员上线前的历史画像（patient_id == username）无需迁移即可继续使用。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from lingyi.api.deps import get_current_user, get_storage
from lingyi.api.schemas import MemberCreate, MemberRename, MemberResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_response(member: Any, username: str) -> MemberResponse:
    """Member -> MemberResponse（is_primary 由 member_id 是否等于账号名推导）。"""
    return MemberResponse(
        member_id=member.member_id,
        display_name=member.display_name,
        created_at=member.created_at,
        is_primary=member.member_id == username,
    )


@router.get("/members", response_model=list[MemberResponse])
async def list_members(
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """列出当前账号的咨询人（主成员在前）；老账号首次访问时补建主成员。"""
    await storage.ensure_primary_member(username)
    members = await storage.list_members(username)
    return [_to_response(m, username) for m in members]


@router.post("/members", response_model=MemberResponse)
async def create_member(
    request: MemberCreate,
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """新建咨询人（归属当前账号）。"""
    name = request.display_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="显示名不能为空")
    member = await storage.create_member(username, name)
    return _to_response(member, username)


@router.patch("/members/{member_id}", response_model=MemberResponse)
async def rename_member(
    member_id: str,
    request: MemberRename,
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """重命名咨询人（仅限归属账号）。"""
    name = request.display_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="显示名不能为空")
    renamed = await storage.rename_member(member_id, name, username)
    if not renamed:
        raise HTTPException(status_code=404, detail="咨询人不存在或不归属当前账号")
    member = await storage.get_member(member_id)
    return _to_response(member, username)


@router.delete("/members/{member_id}")
async def delete_member(
    member_id: str,
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """删除咨询人及其画像、会话（主成员与最后一个咨询人不可删）。"""
    member = await storage.get_member(member_id)
    if member is None or member.username != username:
        raise HTTPException(status_code=404, detail="咨询人不存在或不归属当前账号")
    if member_id == username:
        raise HTTPException(status_code=400, detail="主成员不可删除")
    if not await storage.delete_member(member_id, username):
        raise HTTPException(status_code=400, detail="至少保留一个咨询人")
    return {"status": "ok"}
