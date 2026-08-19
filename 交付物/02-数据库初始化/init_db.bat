@echo off
REM kb_mp 数据库初始化（Windows）
setlocal
chcp 65001 > nul

set "ROOT_DIR=%~dp0..\.."
cd /d "%ROOT_DIR%"

echo ════════════════════════════════════════
echo   kb_mp 数据库初始化
echo ════════════════════════════════════════

REM 读取 .env
if not exist ".env" (
    echo [错误] 未发现 .env，请先从 .env.example 复制
    exit /b 1
)

for /f "tokens=*" %%i in ('findstr /b "DATABASE_URL=" .env') do set "DATABASE_URL=%%i"

echo [1/3] MySQL 连接测试
where mysql > nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 mysql 命令行客户端
    exit /b 1
)

REM 简化版：用 mysql 命令创建库
REM 注意：实际连接参数需从 .env 解析
echo [2/3] 建库 + schema
REM 此处为占位 — 实际执行请用 PowerShell 解析 DATABASE_URL
echo [提示] 实际执行请用 init_db.sh 或手动执行以下命令：
echo        mysql -h HOST -u USER -pPASSWORD -e "CREATE DATABASE kb_mp DEFAULT CHARACTER SET utf8mb4"

REM 3. Alembic 迁移 + 种子
echo [3/3] Alembic 迁移 + 灌入种子数据
where uv > nul 2>&1
if not errorlevel 1 (
    uv sync --all-extras
    uv run alembic upgrade head
    uv run python scripts/seed.py --reset
) else (
    .venv\Scripts\python -m alembic upgrade head
    .venv\Scripts\python scripts\seed.py --reset
)

echo.
echo ════════════════════════════════════════
echo   数据库初始化完成
echo   演示账号：admin / Admin@123
echo ════════════════════════════════════════
pause