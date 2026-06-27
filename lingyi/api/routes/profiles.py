"""画像管理路由 — GET /api/profiles。"""

import logging

from fastapi import APIRouter

from lingyi.api.deps import get_storage
from lingyi.api.schemas import ProfileResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/profiles/{patient_id}", response_model=ProfileResponse)
async def get_profile(patient_id: str):
    """获取患者画像。"""
    storage = get_storage()
    profile = await storage.get_profile(patient_id)
    return ProfileResponse(
        patient_id=profile.patient_id,
        constitution=profile.constitution,
        allergies=profile.allergies,
        past_history=profile.past_history,
    )


@router.get("/profiles", response_model=list[dict])
async def list_profiles():
    """列出所有患者画像。"""
    storage = get_storage()
    return await storage.list_profiles()
