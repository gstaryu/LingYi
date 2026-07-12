"""
文件解析器 - 将用户上传的 PDF/DOCX/TXT 文件解析为纯文本。

设计原则:
- 同步解析库（PyPDF2、python-docx）用 asyncio.to_thread 包装为异步，不阻塞事件循环
- 不支持的类型返回空字符串并记录警告，不抛异常中断图执行
- 解析失败时记录错误并返回空字符串，由调用方决定如何处理
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


class FileParser:
    """文件解析器，支持 PDF / DOCX / TXT。"""

    SUPPORTED_EXTS = {".pdf", ".docx", ".txt"}

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
            return self._parse_txt(file_path)
        except Exception as e:
            logger.error("解析文件失败 %s: %s", file_path, e, exc_info=True)
            return ""

    @staticmethod
    def _parse_pdf(file_path: str) -> str:
        """解析 PDF（使用 PyPDF2）。"""
        from PyPDF2 import PdfReader

        reader = PdfReader(file_path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()

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
