"""画像管理路由 - GET /api/profiles（需认证）。"""

import logging
from typing import Any

from fastapi import APIRouter, Depends

from lingyi.api.deps import get_current_user, get_storage
from lingyi.api.schemas import ProfileResponse

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


@router.get("/profiles", response_model=list[dict])
async def list_profiles(
    storage: Any = Depends(get_storage),
    username: str = Depends(get_current_user),
):
    """列出所有患者画像（需认证，按最后更新时间降序）。"""
    return await storage.list_profiles()
