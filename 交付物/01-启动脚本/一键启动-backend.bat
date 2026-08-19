@echo off
REM kb_mp 后端启动脚本
setlocal
chcp 65001 > nul

set "ROOT_DIR=%~dp0..\.."
cd /d "%ROOT_DIR%"

echo [backend] 切换到 %ROOT_DIR%

REM 检查 .env
if not exist ".env" (
    echo [错误] 未发现 .env，请先从 .env.example 复制
    exit /b 1
)

REM 安装依赖（首次）
if not exist ".venv" (
    echo [backend] 首次启动，创建虚拟环境...
    python -m venv .venv
    .venv\Scripts\python -m pip install --upgrade pip
)

where uv > nul 2>&1
if not errorlevel 1 (
    echo [backend] 使用 uv sync 同步依赖
    uv sync --all-extras
) else (
    echo [backend] 使用 pip 安装依赖
    .venv\Scripts\python -m pip install -e ".[dev]"
)

REM 初始化数据库
echo [backend] 初始化数据库（Alembic upgrade）
uv run alembic upgrade head 2>nul || .venv\Scripts\alembic.exe upgrade head

REM 灌入种子数据（幂等）
echo [backend] 灌入种子数据
uv run python scripts/seed.py

REM 启动 uvicorn
echo [backend] 启动 uvicorn :8000
uv run uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --reload