#!/usr/bin/env bash
# kb_mp 前端启动脚本（macOS / Linux）
set -e

ROOT_DIR="$(cd "$(dirname "$0")/../.."/frontend && pwd)"
cd "$ROOT_DIR"

echo "[frontend] 切换到 $ROOT_DIR"

if [ ! -d "node_modules" ]; then
    echo "[frontend] 首次启动，安装 npm 依赖"
    npm install
fi

echo "[frontend] 启动 vite :5173"
npm run dev