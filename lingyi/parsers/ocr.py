"""
轻量 OCR 引擎适配层。

默认实现为 RapidOCR（ONNXRuntime + PP-OCRv4 mobile），模型随 wheel 内置，
无需联网下载；未安装时返回 NullOcrEngine，调用方自动降级为纯文本解析。

设计原则:
- 懒加载：进程启动不导入 onnxruntime/cv2，首次识别时才加载模型
- 失败不抛异常：识别错误/超时只记日志并返回空串，由调用方决定后续处理
- 通过协议注入：测试可传入假引擎，不加载真实模型
"""

import logging
import threading
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class OcrEngine(Protocol):
    """OCR 引擎协议：输入图片，输出按行拼接的文本。"""

    available: bool

    def extract(self, image: Any) -> str:
        """识别单张图片（PIL.Image 或 ndarray），返回文本（可能为空）。"""


class NullOcrEngine:
    """未安装 OCR 依赖时的空实现：始终返回空文本。"""

    available = False

    def extract(self, image: Any) -> str:
        return ""


class RapidOcrEngine:
    """RapidOCR 实现（ONNXRuntime，CPU）。"""

    available = True

    def __init__(self) -> None:
        self._engine: Any = None
        self._lock = threading.Lock()

    def _ensure_engine(self) -> Any:
        # 双重检查锁：首次识别时才加载模型（约 1~2 秒）
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    from rapidocr_onnxruntime import RapidOCR

                    self._engine = RapidOCR()
                    logger.info("RapidOCR 引擎加载完成")
        return self._engine

    def extract(self, image: Any) -> str:
        try:
            engine = self._ensure_engine()
            result, _elapse = engine(image)
        except Exception as e:  # noqa: BLE001 - OCR 失败不应中断文件解析
            logger.error("OCR 识别失败: %s", e, exc_info=True)
            return ""

        if not result:
            return ""

        lines: list[str] = []
        for item in result:
            # 结果项格式: [box, text, score]
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                text = str(item[1]).strip()
                if text:
                    lines.append(text)
        return "\n".join(lines)


_engine_cache: OcrEngine | None = None
_cache_lock = threading.Lock()


def get_ocr_engine() -> OcrEngine:
    """获取 OCR 引擎单例；依赖缺失时返回 NullOcrEngine（只提示一次）。"""
    global _engine_cache
    if _engine_cache is not None:
        return _engine_cache

    with _cache_lock:
        if _engine_cache is not None:
            return _engine_cache
        try:
            import rapidocr_onnxruntime  # noqa: F401
        except ImportError:
            logger.warning(
                "OCR 不可用：未安装 rapidocr-onnxruntime，图片/扫描版 PDF 将无法识别"
                "（pip install -e . 可安装）"
            )
            _engine_cache = NullOcrEngine()
        else:
            _engine_cache = RapidOcrEngine()
        return _engine_cache
