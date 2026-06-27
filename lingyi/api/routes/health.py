"""健康检查路由。"""

from fastapi import APIRouter

from lingyi.api.schemas import HealthResponse
from lingyi.config import get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查端点。"""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version="2.0.0",
        rag_mode=settings.rag_mode,
    )
