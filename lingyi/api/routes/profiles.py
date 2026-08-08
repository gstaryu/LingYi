"""画像管理路由 - GET/PATCH /api/profiles（需认证）。"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from lingyi.api.deps import get_current_user, get_storage
from lingyi.api.schemas import ProfileResponse, ProfileUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/profiles/{patient_id}", response_model=ProfileResponse)
async def get_profile(
    patient_id: str,
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """获取患者画像（需认证）。"""
    profile = await storage.get_profile(patient_id)
    return ProfileResponse(
        patient_id=profile.patient_id,
        constitution=profile.constitution,
        allergies=profile.allergies,
        past_history=profile.past_history,
    )


@router.patch("/profiles/{patient_id}", response_model=ProfileResponse)
async def update_profile(
    patient_id: str,
    body: ProfileUpdate,
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """更新患者画像（需认证，仅限本人编辑）。

    - allergies: 完整覆盖（非合并），用于手动编辑过敏史
    - constitution: 走 update_profile 合并语义（保留历史）
    """
    if patient_id != username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能修改自己的画像",
        )

    if body.allergies is not None:
        await storage.set_allergies(patient_id, body.allergies)
    if body.constitution is not None and body.constitution.strip():
        await storage.update_profile(patient_id, {"constitution": body.constitution.strip()})

    profile = await storage.get_profile(patient_id)
    return ProfileResponse(
        patient_id=profile.patient_id,
        constitution=profile.constitution,
        allergies=profile.allergies,
        past_history=profile.past_history,
    )


@router.get("/profiles", response_model=list[dict])
async def list_profiles(
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """列出所有患者画像（需认证，按最后更新时间降序）。"""
    return await storage.list_profiles()
