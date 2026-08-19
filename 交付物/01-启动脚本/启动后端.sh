#!/usr/bin/env bash
# kb_mp 后端启动脚本（macOS / Linux）
set -e

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

echo "[backend] 切换到 $ROOT_DIR"

if [ ! -f ".env" ]; then
    echo "[错误] 未发现 .env，请先从 .env.example 复制"
    exit 1
fi

# 安装依赖
if [ ! -d ".venv" ]; then
    echo "[backend] 首次启动，创建虚拟环境"
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
fi

if command -v uv >/dev/null 2>&1; then
    echo "[backend] uv sync 同步依赖"
    uv sync --all-extras
    UV_RUN="uv run"
else
    echo "[backend] pip 安装依赖"
    .venv/bin/pip install -e ".[dev]"
    UV_RUN=".venv/bin"
fi

# 初始化数据库
echo "[backend] 初始化数据库（Alembic upgrade）"
$UV_RUN alembic upgrade head || .venv/bin/alembic upgrade head

# 灌入种子数据
echo "[backend] 灌入种子数据"
$UV_RUN python scripts/seed.py

# 启动 uvicorn
echo "[backend] 启动 uvicorn :8000"
$UV_RUN uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --reload