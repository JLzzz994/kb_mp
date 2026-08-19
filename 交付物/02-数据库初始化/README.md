# 数据库初始化说明

## 方案 A：Alembic（推荐）

Alembic 是项目首选迁移工具，11 张表的 schema 与 `app/infrastructure/database.py` 的 ORM 字段严格对齐。

```bash
# 在项目根目录执行
cd 交付物/02-数据库初始化/
bash init_db.sh        # macOS / Linux
init_db.bat            # Windows
```

底层逻辑：
1. 解析 `.env` 的 `DATABASE_URL`
2. 在 MySQL 中 `CREATE DATABASE kb_mp` (utf8mb4_unicode_ci)
3. 跑 `alembic upgrade head`（执行 `alembic/versions/0001_initial.py`）
4. 跑 `python scripts/seed.py --reset` 灌入 3 部门 + 3 角色 + 17 权限 + 3 用户

## 方案 B：纯 SQL（备选）

如果不想用 Alembic，可直接跑 `kb_mp_schema.sql`：

```bash
mysql -u root -p < kb_mp_schema.sql
```

**注意**：
- SQL 脚本仅建库 + 建表 + 部门/角色/权限；
- **3 个演示用户的密码哈希需要 Python 生成**（bcrypt cost=12）；
- 推荐 SQL 建表后跑 `python scripts/seed.py --reset` 补全用户。

## ���示账号

| 账号 | 密码 | 角色 | 权限 |
|------|------|------|------|
| `admin` | `Admin@123` | 系统管理员 | 全 17 权限 |
| `kadmin` | `Kadmin@123` | 知识管理员 | 11 权限（无用户/角色/部门管理）|
| `alice` | `Alice@123` | 普通用户 | 4 权限（仅 AI + 知识查询）|

## 17 权限码清单

```
user:read                      # 用户查询
user:write                     # 用户增删改
role:read                      # 角色查询
role:write                     # 角色权限分配
dept:read                      # 部门查询
dept:write                     # 部门增删改
knowledge:read                 # 知识单元查询
knowledge:write                # 知识单元新增 / 修改
knowledge:delete               # 知识单元删除
knowledge:assign_permission    # 知识四维权限配置
knowledge:check                # 知识鉴权检查
ai:chat                        # AI 问答
dashboard:read                 # 数据看板
faq:read                       # FAQ 查询
faq:write                      # FAQ 增删改
faq:review                     # FAQ 审核（发布/驳回）
gap:read                       # 知识缺口查询
```

## Redis 注意事项

鉴权位图（5 分钟 TTL）和 FAQ 缓存依赖 Redis：

```bash
# 启动 Redis（Docker）
docker run -d -p 6379:6379 --name kb_mp-redis redis:7-alpine
```

`.env` 中 `REDIS_URL=redis://localhost:6379/0`。
如果 Redis 不可用，鉴权会回退到 MySQL 查询（仍可用）。

## Milvus 注意事项

向量检索依赖 Milvus 2.5+（演示期可用 mock；生产需 Milvus 服务）。

```bash
# Milvus 单机版（仅 Linux）
docker run -d -p 19530:19530 milvusdb/milvus:v2.5.4 ...
```

`.env` 中：
```
embedding_backend=local_bge       # 本地 BGE-M3（推荐演示期）
milvus_url=http://localhost:19530
```

如果 Milvus 不可用，AI 问答会回退到纯数据库查询（无向量召回，仅关键字）。