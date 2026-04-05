import os


class FileParser:
    """
    增强版文件解析工具，支持多种格式的医疗文档。
    要求安装: pip install PyPDF2 python-docx
    """

    def parse_file(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            print(f"⚠️ 文件未找到: {file_path}")
            return ""

        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == ".txt":
                return self._parse_txt(file_path)
            elif ext == ".pdf":
                return self._parse_pdf(file_path)
            elif ext in [".docx", ".doc"]:
                return self._parse_docx(file_path)
            else:
                print(f"❌ 不支持的文件格式: {ext}")
                return ""
        except ImportError as e:
            msg = "❌ 缺少依赖库。请运行: pip install PyPDF2 python-docx"
            print(msg)
            return msg
        except Exception as e:
            print(f"❌ 解析文件 {os.path.basename(file_path)} 失败: {e}")
            return f"解析失败: {str(e)}"

    def _parse_txt(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def _parse_pdf(self, file_path: str) -> str:
        import PyPDF2
        text = ""
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    def _parse_docx(self, file_path: str) -> str:
        # 注意：这里必须是 python-docx 库提供的 docx 模块
        from docx import Document
        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])


# 导出实例
file_parser = FileParser()