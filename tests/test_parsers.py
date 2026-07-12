"""
文件解析器测试 - 验证 FileParser 的 TXT 解析与异常处理。

PDF/DOCX 依赖二进制样本，此处仅测 TXT 路径与边界（类型/不存在）。
"""

import pytest

from lingyi.parsers.file_parser import FileParser


class TestFileParser:
    """FileParser 测试套件。"""

    @pytest.fixture
    def parser(self) -> FileParser:
        return FileParser()

    async def test_parse_txt_utf8(self, parser, tmp_path):
        """UTF-8 文本应正确解析。"""
        p = tmp_path / "note.txt"
        p.write_text("患者主诉：发热恶寒", encoding="utf-8")
        text = await parser.aparse_file(str(p))
        assert "发热恶寒" in text

    async def test_parse_txt_gbk_fallback(self, parser, tmp_path):
        """GBK 编码应通过回退正确解析。"""
        p = tmp_path / "gbk.txt"
        p.write_bytes("脾胃虚寒".encode("gbk"))
        text = await parser.aparse_file(str(p))
        assert "脾胃虚寒" in text

    async def test_unsupported_type_returns_empty(self, parser, tmp_path):
        """不支持的文件类型应返回空字符串。"""
        p = tmp_path / "data.csv"
        p.write_text("a,b,c", encoding="utf-8")
        assert await parser.aparse_file(str(p)) == ""

    async def test_nonexistent_returns_empty(self, parser):
        """不存在的文件应返回空字符串，不抛异常。"""
        assert await parser.aparse_file("/no/such/file.txt") == ""
