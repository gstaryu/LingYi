"""
文档解析技能 — 解析用户上传的文件（PDF/DOCX/TXT）。

在 LangGraph 图中作为第一个节点执行，负责:
1. 检测 state 中的 input_files
2. 调用 FileParser 解析文件内容
3. 将解析结果存入 state 的 extracted_file_content 字段
4. 缓存已解析文件，避免重复解析
"""

import logging
from typing import Any

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class ReaderSkill(BaseSkill):
    """
    文档解析技能节点。

    不依赖 LLM，仅调用 FileParser 解析上传的文件。
    通过 parsed_files 缓存机制避免重复解析。
    """

    def __init__(self, file_parser: Any = None):
        """
        初始化文档解析技能。

        Args:
            file_parser: FileParser 实例，支持 parse_file(path) -> str
        """
        # Reader 不需要 LLM，传 None
        super().__init__(llm=None)
        self.file_parser = file_parser

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        解析用户上传的文件。

        Args:
            state: AgentState，需包含 input_files 和 parsed_files 字段

        Returns:
            更新后的 extracted_file_content 和 parsed_files
        """
        input_files = state.get("input_files", [])
        parsed_files = set(state.get("parsed_files", []))

        if not input_files or not self.file_parser:
            return {}

        # 过滤已解析的文件
        new_files = [f for f in input_files if f not in parsed_files]
        if not new_files:
            return {}

        # 解析新文件
        contents: list[str] = []
        for file_path in new_files:
            try:
                content = await self.file_parser.aparse_file(file_path)
                if content:
                    contents.append(content)
                    parsed_files.add(file_path)
                    logger.info("文件解析成功: %s (%d 字符)", file_path, len(content))
            except Exception as e:
                logger.warning("文件解析失败 %s: %s", file_path, e)

        # 合并到已有内容
        existing = state.get("extracted_file_content", "")
        all_content = existing + "\n\n".join(contents) if contents else existing

        return {
            "extracted_file_content": all_content,
            "parsed_files": list(parsed_files),
        }
