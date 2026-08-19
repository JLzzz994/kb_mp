#!/usr/bin/env bash
# ============================================
# kb_mp 一键启动脚本（macOS / Linux）
# ============================================
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "════════════════════════════════════════"
echo "  kb_mp 一键启动"
echo "════════════════════════════════════════"

# ── 1. 检查 Python ─────────────────────────────
echo "[1/5] 检查 Python"
if ! command -v python3 >/dev/null 2>&1; then
    echo "[错误] 未检测到 python3，请先安装 Python 3.12+"
    exit 1
fi
python3 --version

if ! command -v uv >/dev/null 2>&1; then
    echo "[警告] 未检测到 uv，将使���系统 Python"
fi

# ── 2. 检查 Node ─────────────────────────────
echo "[2/5] 检查 Node"
if ! command -v node >/dev/null 2>&1; then
    echo "[警告] 未检测到 Node.js，前端将无法启动"
fi
node --version 2>/dev/null || true

# ── 3. .env ─────────────────────────────
echo "[3/5] 检查 .env"
if [ ! -f ".env" ]; then
    echo "[信息] 未发现 .env，从 .env.example 复制"
    cp .env.example .env
fi

# ── 4. 启动后端 ─────────────────────────────
echo "[4/5] 启动后端（uvicorn :8000）"
bash 交付物/01-启动脚本/启动后端.sh &
BACKEND_PID=$!

sleep 3

# ── 5. 启动前端 ─────────────────────────────
echo "[5/5] 启动前端（vite :5173）"
bash 交付物/01-启动脚本/启动前端.sh &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

echo ""
echo "════════════════════════════════════════"
echo "  启动完成"
echo "  后端：http://127.0.0.1:8000/docs"
echo "  前端：http://127.0.0.1:5173"
echo "  演示账号：admin / Admin@123"
echo "════════════════════════════════════════"
wait