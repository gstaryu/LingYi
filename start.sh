#!/usr/bin/env bash
# 灵医一键启动脚本（Linux / macOS / Git Bash）
# 用法：./start.sh
# 后端 FastAPI :8000 + 前端 Next.js :3000，日志输出到 storage/
set -e
cd "$(dirname "$0")"

mkdir -p storage

echo "=== 激活 conda 环境 lingyi ==="
conda activate lingyi 2>/dev/null || source activate lingyi 2>/dev/null || true

if [ ! -f .env ]; then
    echo "⚠️ 未找到 .env，请先配置 LLM API Key（参考 README）"
fi

if [ ! -d frontend/node_modules ]; then
    echo "=== 前端依赖未安装，正在 npm install ==="
    (cd frontend && npm install)
fi

echo "=== 启动后端 (FastAPI :8000) ==="
uvicorn lingyi.api.app:app --port 8000 > storage/backend.log 2>&1 &
BACKEND_PID=$!
echo "后端 PID: $BACKEND_PID (日志: storage/backend.log)"

sleep 2

echo "=== 启动前端 (Next.js :3000) ==="
(cd frontend && npm run dev > ../storage/frontend.log 2>&1) &
FRONTEND_PID=$!
echo "前端 PID: $FRONTEND_PID (日志: storage/frontend.log)"

echo ""
echo "✅ 启动完成："
echo "   前端: http://localhost:3000"
echo "   后端: http://localhost:8000/api/health"
echo "   停止: kill $BACKEND_PID $FRONTEND_PID"
echo "   或: pkill -f uvicorn; pkill -f 'next dev'"
