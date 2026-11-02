"""
文件解析器 - 将用户上传的文件解析为纯文本。

支持 PDF / DOCX / TXT 与图片（PNG/JPG/JPEG/WEBP/BMP）。
扫描版 PDF 与图片通过轻量 OCR（RapidOCR）识别；未安装 OCR 时自动降级为纯文本。

设计原则:
- 同步解析库（pypdf、python-docx、OCR）用 asyncio.to_thread 包装为异步，不阻塞事件循环
- 不支持的类型返回空字符串并记录警告，不抛异常中断图执行
- OCR 结果加统一标记，避免下游把识别错误当作事实
"""

import asyncio
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

# OCR 结果统一前缀（提示下游模型这是识别文本，可能有误差）
OCR_MARKER = "【OCR识别，可能存在误差】"

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class FileParser:
    """文件解析器，支持 PDF / DOCX / TXT / 图片（OCR）。"""

    SUPPORTED_EXTS = {".pdf", ".docx", ".txt"} | _IMAGE_EXTS

    def __init__(self, ocr_engine: Any = None, settings: Any = None):
        """
        初始化解析器。

        Args:
            ocr_engine: 可选 OCR 引擎（测试注入）；None 时首次识别再懒加载
            settings: 可选 Settings 实例；None 时懒加载全局配置
        """
        self._ocr_engine = ocr_engine
        self._settings = settings

    # ==================== 依赖懒加载 ====================

    def _get_settings(self) -> Any:
        if self._settings is None:
            from lingyi.config import get_settings

            self._settings = get_settings()
        return self._settings

    def _get_ocr(self) -> Any:
        if self._ocr_engine is None:
            from lingyi.parsers.ocr import get_ocr_engine

            self._ocr_engine = get_ocr_engine()
        return self._ocr_engine

    # ==================== 对外入口 ====================

    async def aparse_file(self, file_path: str) -> str:
        """
        异步解析文件为纯文本。

        Args:
            file_path: 文件路径

        Returns:
            解析后的纯文本；文件不存在、类型不支持或解析失败时返回空字符串
        """
        if not os.path.exists(file_path):
            logger.warning("文件不存在: %s", file_path)
            return ""

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.SUPPORTED_EXTS:
            logger.warning("不支持的文件类型 %s（仅支持 %s）", ext, self.SUPPORTED_EXTS)
            return ""

        # 同步解析在线程池中执行，避免阻塞事件循环
        return await asyncio.to_thread(self._parse_sync, file_path, ext)

    def _parse_sync(self, file_path: str, ext: str) -> str:
        """同步解析分发（在线程池中运行）。"""
        try:
            if ext == ".pdf":
                return self._parse_pdf(file_path)
            if ext == ".docx":
                return self._parse_docx(file_path)
            if ext == ".txt":
                return self._parse_txt(file_path)
            return self._parse_image(file_path)
        except Exception as e:
            logger.error("解析文件失败 %s: %s", file_path, e, exc_info=True)
            return ""

    # ==================== OCR ====================

    def _ocr_image(self, image: Any) -> str:
        """对单张图片执行 OCR（带超时）；不可用或失败时返回空串。"""
        engine = self._get_ocr()
        if not getattr(engine, "available", True):
            return ""

        timeout = self._get_settings().ocr_timeout_seconds
        box: dict[str, Any] = {}

        def _run() -> None:
            try:
                box["text"] = engine.extract(image)
            except Exception as e:  # noqa: BLE001 - OCR 失败不影响其余页面
                logger.error("OCR 执行失败: %s", e, exc_info=True)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout)
        if worker.is_alive():
            logger.warning("OCR 超时（>%ss），跳过该页", timeout)
            return ""
        return str(box.get("text") or "").strip()

    def _parse_image(self, file_path: str) -> str:
        """解析图片：缩放后 OCR。"""
        if not self._get_settings().ocr_enabled:
            logger.info("OCR 已禁用，跳过图片: %s", file_path)
            return ""

        from PIL import Image

        with Image.open(file_path) as img:
            img = img.convert("RGB")
            max_side = self._get_settings().ocr_max_image_side
            longest = max(img.size)
            if longest > max_side:
                ratio = max_side / longest
                img = img.resize(
                    (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                    Image.LANCZOS,
                )
            text = self._ocr_image(img)

        if not text:
            logger.warning("图片未识别出文本: %s", file_path)
            return ""
        logger.info("图片 OCR 完成: %s（%d 字）", file_path, len(text))
        return f"{OCR_MARKER}\n{text}"

    # ==================== PDF ====================

    def _parse_pdf(self, file_path: str) -> str:
        """解析 PDF：文本足够的页用提取文本，不足的页改用 OCR。"""
        texts = self._extract_pdf_pages_text(file_path)
        settings = self._get_settings()

        if not settings.ocr_enabled:
            return "\n".join(t for t in texts if t).strip()

        min_chars = settings.ocr_min_text_chars
        max_pages = settings.ocr_max_pages

        # 全部页面文本充足时不做任何 OCR（避免无谓开销）
        if all(len((t or "").strip()) >= min_chars for t in texts):
            return "\n".join(t for t in texts if t).strip()

        doc: Any = None
        ocr_pages = 0
        out: list[str] = []
        try:
            for idx, text in enumerate(texts):
                stripped = (text or "").strip()
                if len(stripped) >= min_chars:
                    out.append(stripped)
                    continue
                if ocr_pages >= max_pages:
                    logger.info("已达 OCR 页数上限 %d，剩余页面仅保留提取文本", max_pages)
                    out.append(stripped)
                    continue

                if doc is None:
                    doc = self._open_pdf(file_path)
                image = self._render_pdf_page(doc, idx)
                ocr_text = self._ocr_image(image) if image is not None else ""

                if ocr_text:
                    out.append(f"{OCR_MARKER}\n{ocr_text}")
                    ocr_pages += 1
                    logger.info(
                        "PDF 第 %d 页文本不足，已用 OCR 识别（%d 字）", idx + 1, len(ocr_text)
                    )
                else:
                    out.append(stripped)
        finally:
            if doc is not None:
                try:
                    doc.close()
                except Exception:  # noqa: BLE001 - 关闭失败无需中断解析
                    pass

        return "\n".join(t for t in out if t).strip()

    @staticmethod
    def _extract_pdf_pages_text(file_path: str) -> list[str]:
        """用 pypdf 提取每页文本（保持与页号一一对应）。"""
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        return [page.extract_text() or "" for page in reader.pages]

    @staticmethod
    def _open_pdf(file_path: str) -> Any:
        """打开 PDF 用于栅格化（pypdfium2，无需 poppler）。"""
        import pypdfium2 as pdfium

        return pdfium.PdfDocument(file_path)

    def _render_pdf_page(self, doc: Any, index: int) -> Any:
        """把 PDF 第 index 页渲染为 PIL 图片；失败返回 None。"""
        try:
            page = doc[index]
            dpi = self._get_settings().ocr_dpi
            bitmap = page.render(scale=dpi / 72)
            return bitmap.to_pil()
        except Exception as e:  # noqa: BLE001 - 单页渲染失败不影响其它页
            logger.error("PDF 第 %d 页栅格化失败: %s", index + 1, e)
            return None

    # ==================== DOCX / TXT ====================

    @staticmethod
    def _parse_docx(file_path: str) -> str:
        """解析 DOCX（使用 python-docx）。"""
        from docx import Document

        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    @staticmethod
    def _parse_txt(file_path: str) -> str:
        """解析 TXT（UTF-8，回退 GBK）。"""
        for encoding in ("utf-8", "gbk"):
            try:
                with open(file_path, encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        return ""
