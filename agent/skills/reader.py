import os
from agent.state import AgentState
from tools.file_parser import file_parser


def reader_node(state: AgentState):
    """
    文档解析节点：将物理文件转化为 state 中的字符串
    """
    input_files = state.get("input_files", [])
    parsed_files = state.get("parsed_files", [])

    if not input_files:
        return {"extracted_file_content": "", "parsed_files": []}

    # 【修复】检测当前上传文件集合与已经解析的文件集合是否一致
    if set(input_files) == set(parsed_files):
        print("--- 📄 文档缓存存在且无变化，跳过物理扫描 ---")
        return {}

    print(f"--- 📄 正在物理扫描文件: {input_files} ---")

    contents = []
    for f_path in input_files:
        text = file_parser.parse_file(f_path)
        if text:
            contents.append(f"【文件: {os.path.basename(f_path)}】\n{text}")

    combined_content = "\n\n".join(contents)

    return {
        "extracted_file_content": combined_content,
        "parsed_files": input_files
    }