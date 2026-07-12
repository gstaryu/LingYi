"""文件上传路由 - POST /api/upload。

用户上传病历等文件（PDF/DOCX/TXT），保存到 storage/uploads/{username}/，
返回服务端路径，供 /api/chat 的 files 字段使用，由 ReaderSkill/FileParser 解析。
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from lingyi.api.deps import get_current_user
from lingyi.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

# 允许的文件类型（与 FileParser 支持的范围一致）
_ALLOWED_EXTS = {".pdf", ".docx", ".txt"}
# 单文件大小上限（10MB）
_MAX_SIZE = 10 * 1024 * 1024


@router.post("/upload")
async def upload_file(
    file: UploadFile,
    username: str = Depends(get_current_user),
) -> JSONResponse:
    """
    上传单个文件，返回服务端路径。

    Returns:
        {"path": "<服务端绝对路径>", "filename": "<原始文件名>"}
    """
    import os

    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {ext}，仅支持 {sorted(_ALLOWED_EXTS)}",
        )

    # 读取并校验大小
    content = await file.read()
    if len(content) > _MAX_SIZE:
        raise HTTPException(status_code=413, detail="文件过大（上限 10MB）")

    settings = get_settings()
    user_dir = os.path.join(settings.uploads_dir, username)
    os.makedirs(user_dir, exist_ok=True)

    # 用 uuid 前缀防重名，保留原始扩展名
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    save_path = os.path.join(user_dir, safe_name)
    with open(save_path, "wb") as f:
        f.write(content)

    logger.info("文件上传成功: user=%s, file=%s -> %s", username, file.filename, save_path)
    return JSONResponse({"path": save_path, "filename": file.filename})
