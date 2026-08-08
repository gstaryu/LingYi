# 灵医后端开发启动脚本（UTF-8 安全）
# 确保 Windows 控制台 + Python 均使用 UTF-8，解决中文日志乱码问题。
# 用法: 在项目根目录运行 .\scripts\dev_backend.ps1

# Python 强制 UTF-8 模式（覆盖所有 stdin/stdout/stderr 编码）
$env:PYTHONUTF8 = "1"

# 多智能体模式
$env:AGENT_MODE = "multiagent"

# Windows 控制台代码页切换为 UTF-8（65001）
chcp 65001 | Out-Null

# 激活 conda 环境
conda activate lingyi

# 启动 FastAPI 后端
uvicorn lingyi.api.app:app --port 8000 --log-level info
