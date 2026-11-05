# 启动自托管 Langfuse（Docker Desktop + docker compose）
# 用法：
#   .\deploy\langfuse\start.ps1          # 启动容器栈，立即返回
#   .\deploy\langfuse\start.ps1 -Wait    # 启动后等健康检查通过再返回
#
# Docker 未运行时自动拉起 Docker Desktop 并等待引擎就绪。

param([switch]$Wait)

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    function Find-DockerBin {
        $candidates = @(
            "$env:ProgramFiles\Docker\Docker\resources\bin",
            "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin"
        )
        foreach ($p in $candidates) {
            if (Test-Path (Join-Path $p "docker.exe")) { return $p }
        }
        return $null
    }

    function Test-DockerEngine {
        docker info --format "{{.ServerVersion}}" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    }

    $binDir = Find-DockerBin
    if (-not $binDir) {
        Write-Host "未找到 Docker Desktop，请先安装：https://www.docker.com/products/docker-desktop/" -ForegroundColor Red
        exit 1
    }
    $env:PATH = "$binDir;" + $env:PATH

    if (-not (Test-DockerEngine)) {
        $desktop = @(
            "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
            "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
        ) | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $desktop) {
            Write-Host "Docker 引擎未运行，且找不到 Docker Desktop.exe" -ForegroundColor Red
            exit 1
        }
        Write-Host "启动 Docker Desktop，等待引擎就绪..." -ForegroundColor Cyan
        Start-Process $desktop
        $ready = $false
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 5
            if (Test-DockerEngine) { $ready = $true; break }
        }
        if (-not $ready) {
            Write-Host "Docker 引擎 5 分钟内未就绪" -ForegroundColor Red
            exit 1
        }
    }

    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "已从 .env.example 生成 .env（仅本地开发默认口令）" -ForegroundColor Yellow
    }

    $port = 3001
    $envLine = Select-String -Path ".env" -Pattern '^LANGFUSE_PORT=(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($envLine) { $port = [int]$envLine.Matches[0].Groups[1].Value }

    Write-Host "启动 Langfuse 容器..." -ForegroundColor Cyan
    docker compose up -d
    if ($LASTEXITCODE -ne 0) {
        Write-Host "docker compose up 失败" -ForegroundColor Red
        exit 1
    }

    if ($Wait) {
        Write-Host "等待 Langfuse 健康检查..." -ForegroundColor Cyan
        for ($i = 0; $i -lt 40; $i++) {
            try {
                $r = Invoke-WebRequest "http://localhost:$port/api/public/health" -TimeoutSec 5 -UseBasicParsing
                if ($r.StatusCode -eq 200) {
                    Write-Host "Langfuse 就绪: http://localhost:$port" -ForegroundColor Green
                    exit 0
                }
            } catch { }
            Start-Sleep -Seconds 5
        }
        Write-Host "Langfuse 健康检查超时: http://localhost:$port" -ForegroundColor Yellow
        exit 1
    }

    Write-Host "Langfuse 已启动: http://localhost:$port" -ForegroundColor Green
    exit 0
}
finally {
    Pop-Location
}
