# kb_mp 部署指南

## 快速启动（5 分钟）

```bash
# 1. 准备 .env（必填 OPENAI_API_KEY）
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY 与 JWT_SECRET

# 2. 启动 4 个核心服务（mysql / redis / milvus / app）
docker compose up -d mysql redis etcd minio milvus app

# 3. 等待健康（约 30s）
docker compose ps

# 4. 初始化数据库（alembic + seed）
docker compose exec app alembic upgrade head
docker compose exec app python scripts/seed.py

# 5. 验证
curl http://localhost:8000/health
# {"status":"ok","app_name":"kb-mp"}

curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123"}'
# 返回 access_token + user_info + 17 个权限码
```

## 启动 Milvus 可视化（attu）

```bash
docker compose --profile dev up -d attu
# 浏览器访问 http://localhost:8000
```

## 完整清理（含数据卷）

```bash
docker compose down -v
```

## 服务端口

| 服务 | 端口 | 用途 |
| --- | --- | --- |
| app | 8000 | FastAPI HTTP |
| mysql | 3306 | 主库 |
| redis | 6379 | 鉴权位图 + FAQ 缓存 |
| milvus | 19530 | gRPC 向量检索 |
| milvus | 9091 | HTTP 管理 |
| attu | 8000+ | Milvus 可视化（仅 dev） |
| etcd | 2379 | Milvus 内部 |
| minio | 9000/9001 | Milvus 内部对象存储 |

## 服务依赖

```
app  ← mysql, redis, milvus
milvus  ← etcd, minio
```

`docker-compose.yml` 通过 `depends_on: condition: service_healthy` 自动按序启动。

## 数据卷

```
kb_mp_mysql_data      MySQL
kb_mp_redis_data      Redis AOF
milvus_etcd_data      Milvus 元数据
milvus_minio_data     Milvus 对象存储
milvus_data          Milvus 向量
kb_mp_storage        上传文件
```

## 故障排查

详见 `docs/概要设计总纲.md` §11 风险 + ADR-0003 Redis fast-fail。

## 下一步

P0 编码完成后 → 进入 P1（M3 知识资产管理）→ drizzle 阶段时增量 docker-compose 加 monitor / 探针。
