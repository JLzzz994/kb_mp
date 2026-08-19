@echo off
REM ============================================
REM kb_mp 一键启动脚本（Windows）
REM 用法：双击或 cmd 执行
REM 功能：检查环境 → 启动 MySQL/Redis（若本地）→ 启动后端 → 启动前端
REM ============================================

setlocal
chcp 65001 > nul

set "ROOT_DIR=%~dp0.."
cd /d "%ROOT_DIR%"

echo.
echo ════════════════════════════════════════
echo   kb_mp 一键启动
echo ════════════════════════════════════════
echo.

REM ── 1. 环境检查 ─────────────────────────────
echo [1/5] 检查 Python 环境
where python > nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.12+
    pause
    exit /b 1
)
python --version

where uv > nul 2>&1
if errorlevel 1 (
    echo [警告] 未检测到 uv，将使用系统 Python
) else (
    echo [信息] uv 已就绪
)

echo.
echo [2/5] 检查 Node 环境
where node > nul 2>&1
if errorlevel 1 (
    echo [警告] 未检测到 Node.js，前端将无法启动
    echo        安装 Node.js 18+ 后重新运行
) else (
    node --version
)

REM ── 2. 检查 .env ─────────────────────────────
echo.
echo [3/5] 检查 .env 配置
if not exist ".env" (
    echo [信息] 未发现 .env，正在从 .env.example 复制
    copy /Y ".env.example" ".env" > nul
    echo [提示] 请根据实际环境修改 .env 中的 DATABASE_URL / REDIS_URL
    echo        按任意键继续，或 Ctrl+C 中断
    pause > nul
)

REM ── 3. 启动后端 ─────────────────────────────
echo.
echo [4/5] 启动后端（uvicorn :8000）
start "kb_mp-backend" cmd /c "call 一键启动-backend.bat"

REM ── 4. 启动前端 ─────────────────────────────
echo [5/5] 启动前端（vite :5173）
timeout /t 3 /nobreak > nul
start "kb_mp-frontend" cmd /c "call 一键启动-frontend.bat"

echo.
echo ════════════════════════════════════════
echo   启动完成
echo   后端：http://127.0.0.1:8000/docs
echo   前端：http://127.0.0.1:5173
echo   演示账号：admin / Admin@123
echo ════════════════════════════════════════
echo.
pause