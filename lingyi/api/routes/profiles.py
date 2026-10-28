"""画像管理路由 - GET/PATCH /api/profiles（需认证，按咨询人隔离）。"""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from lingyi.api.deps import get_current_user, get_storage
from lingyi.api.schemas import ProfileResponse, ProfileUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_response(profile: Any) -> ProfileResponse:
    """UserProfile -> ProfileResponse（年龄按当前年份换算）。"""
    return ProfileResponse(
        patient_id=profile.patient_id,
        constitution=profile.constitution,
        allergies=profile.allergies,
        past_history=profile.past_history,
        birth_year=profile.birth_year,
        age=profile.age,
        gender=profile.gender,
        medical_history=profile.medical_history,
    )


async def _authorize_member(storage: Any, username: str, patient_id: str) -> None:
    """
    校验 patient_id 是当前账号的咨询人；否则 404。

    主成员（patient_id == username）在缺失时懒创建，保证老账号直接读写画像可用。
    """
    if patient_id == username:
        await storage.ensure_primary_member(username)
        return
    member = await storage.get_member(patient_id)
    if member is None or member.username != username:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="咨询人不存在或不归属当前账号",
        )


@router.get("/profiles/{patient_id}", response_model=ProfileResponse)
async def get_profile(
    patient_id: str,
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """获取咨询人画像（需认证，仅限本账号的咨询人）。"""
    await _authorize_member(storage, username, patient_id)
    profile = await storage.get_profile(patient_id)
    return _to_response(profile)


@router.patch("/profiles/{patient_id}", response_model=ProfileResponse)
async def update_profile(
    patient_id: str,
    body: ProfileUpdate,
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """更新咨询人画像（需认证，仅限本账号的咨询人）。

    - allergies: 完整覆盖（非合并），用于手动编辑过敏史
    - constitution: 走 update_profile 合并语义（保留历史）
    """
    await _authorize_member(storage, username, patient_id)

    if body.allergies is not None:
        await storage.set_allergies(patient_id, body.allergies)
    if body.constitution is not None and body.constitution.strip():
        await storage.update_profile(patient_id, {"constitution": body.constitution.strip()})

    # 人口学与病史：覆盖语义（手动编辑以用户输入为准）
    fields: dict[str, Any] = {}
    if body.birth_year is not None:
        fields["birth_year"] = body.birth_year
    elif body.age is not None:
        fields["birth_year"] = date.today().year - body.age
    if body.gender is not None:
        fields["gender"] = body.gender
    if body.medical_history is not None:
        fields["medical_history"] = [item.model_dump() for item in body.medical_history]
    if fields:
        await storage.set_profile_fields(patient_id, fields)

    profile = await storage.get_profile(patient_id)
    return _to_response(profile)


@router.get("/profiles", response_model=list[dict])
async def list_profiles(
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """列出本账号咨询人的画像（按最后更新时间降序）。"""
    return await storage.list_profiles(username)
