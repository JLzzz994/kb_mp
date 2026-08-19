@echo off
REM kb_mp 前端启动脚本
setlocal
chcp 65001 > nul

set "ROOT_DIR=%~dp0..\..\frontend"
cd /d "%ROOT_DIR%"

echo [frontend] 切换到 %ROOT_DIR%

REM 安装依赖（首次）
if not exist "node_modules" (
    echo [frontend] 首次启动，安装 npm 依赖
    call npm install
)

REM 启动 vite
echo [frontend] 启动 vite :5173（API 代理 → http://localhost:8000）
call npm run dev