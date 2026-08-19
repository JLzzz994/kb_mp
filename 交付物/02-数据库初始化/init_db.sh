#!/usr/bin/env bash
# kb_mp 数据库初始化（macOS / Linux）
# 流程：建库 → 跑 Alembic 迁移 → 灌种子数据
set -e

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

echo "════════════════════════════════════════"
echo "  kb_mp 数据库初始化"
echo "════════════════════════════════════════"

# 读取 .env 获取 DATABASE_URL
if [ -f ".env" ]; then
    export $(grep -E '^DATABASE_URL=' .env | xargs)
    export $(grep -E '^REDIS_URL=' .env | xargs 2>/dev/null || true)
fi

if [ -z "$DATABASE_URL" ]; then
    echo "[错误] 未配置 DATABASE_URL，请先复制 .env.example 到 .env"
    exit 1
fi

# 解析 MySQL 连接参数
DB_USER=$(echo "$DATABASE_URL" | sed -E 's|.*mysql\+aiomysql://([^:]+):.*|\1|')
DB_PASS=$(echo "$DATABASE_URL" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')
DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:]+):.*|\1|')
DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*:([0-9]+)/.*|\1|')
DB_NAME=$(echo "$DATABASE_URL" | sed -E 's|.*/([^?]+).*|\1|')

echo "[1/3] MySQL 连接：$DB_HOST:$DB_PORT 用户 $DB_USER"

# 检查 MySQL 可达
if ! command -v mysql >/dev/null 2>&1; then
    echo "[错误] 未检测到 mysql 命令行客户端"
    exit 1
fi

# 1. 建库（utf8mb4）
echo "[2/3] 建库 + schema"
mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" \
    -e "DROP DATABASE IF EXISTS $DB_NAME; CREATE DATABASE $DB_NAME DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" \
    2>/dev/null || mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" \
    -e "DROP DATABASE IF EXISTS $DB_NAME; CREATE DATABASE $DB_NAME DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 2. 跑 Alembic
echo "[3/3] Alembic 迁移 + 灌入种子数据"
if command -v uv >/dev/null 2>&1; then
    uv sync --all-extras >/dev/null 2>&1
    uv run alembic upgrade head
    uv run python scripts/seed.py --reset
else
    .venv/bin/pip install -e ".[dev]" >/dev/null 2>&1
    .venv/bin/alembic upgrade head
    .venv/bin/python scripts/seed.py --reset
fi

echo ""
echo "════════════════════════════════════════"
echo "  数据库初始化完成"
echo "  演示账号："
echo "    admin / Admin@123    （系统管理员）"
echo "    kadmin / Kadmin@123  （知识管理员）"
echo "    alice / Alice@123    （普通用户）"
echo "════════════════════════════════════════"