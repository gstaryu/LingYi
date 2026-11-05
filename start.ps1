# 灵医一键启动脚本（Windows PowerShell）
# 用法：.\start.ps1
# 启动后端（FastAPI :8000）+ 前端（Next.js :3000），各开一个窗口
# 默认 AGENT_MODE=multiagent（多智能体会诊）、PYTHONUTF8=1（中文日志不乱码）

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Python 强制 UTF-8 + 多智能体模式
$env:PYTHONUTF8 = "1"
$env:AGENT_MODE = "multiagent"

# Windows 控制台代码页切到 UTF-8
chcp 65001 | Out-Null

# 激活 conda 环境
if ($env:CONDA_DEFAULT_ENV -ne "lingyi") {
    Write-Host "激活 conda 环境 lingyi..." -ForegroundColor Cyan
    conda activate lingyi
}

# 检查 .env
if (-not (Test-Path .env)) {
    Write-Host "⚠️ 未找到 .env，请先配置 OPENAI_API_KEY（参考 README）" -ForegroundColor Yellow
}

# 可选：ENABLE_LANGFUSE=true 时拉起自托管 Langfuse（失败不影响问诊）
$langfuseEnabled = Select-String -Path .env -Pattern '^ENABLE_LANGFUSE=(true|1)$' -ErrorAction SilentlyContinue
$langfusePort = "3001"
if ($langfuseEnabled) {
    $portLine = Select-String -Path .env -Pattern '^LANGFUSE_HOST=.*:(\d+)\s*$' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($portLine) { $langfusePort = $portLine.Matches[0].Groups[1].Value }
    Write-Host "启动 Langfuse（自托管链路追踪）..." -ForegroundColor Cyan
    try {
        & "$PSScriptRoot\deploy\langfuse\start.ps1"
    } catch {
        Write-Host "⚠️ Langfuse 启动失败，后端继续运行（追踪数据将丢失，不影响问诊）" -ForegroundColor Yellow
    }
}

# 检查前端依赖
if (-not (Test-Path frontend\node_modules)) {
    Write-Host "前端依赖未安装，正在 npm install..." -ForegroundColor Cyan
    Push-Location frontend
    npm install
    Pop-Location
}

Write-Host "启动后端（FastAPI :8000, AGENT_MODE=multiagent）..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:PYTHONUTF8='1'; `$env:AGENT_MODE='multiagent'; conda activate lingyi; uvicorn lingyi.api.app:app --port 8000"

Start-Sleep -Seconds 2

Write-Host "启动前端（Next.js :3000）..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev"

Write-Host ""
Write-Host "✅ 启动完成：" -ForegroundColor Green
Write-Host "   前端: http://localhost:3000" -ForegroundColor White
Write-Host "   后端: http://localhost:8000/api/health" -ForegroundColor White
if ($langfuseEnabled) {
    Write-Host "   追踪: http://localhost:$langfusePort （Langfuse）" -ForegroundColor White
}
Write-Host "   模式: 多智能体会诊（AGENT_MODE=multiagent）" -ForegroundColor White
Write-Host "   停止: 关闭弹出的两个窗口" -ForegroundColor Gray
