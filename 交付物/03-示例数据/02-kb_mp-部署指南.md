# kb_mp 部署指南

## 一、本地开发部署

### 1.1 依赖

- Python 3.12+
- Node.js 18+
- MySQL 8.0+
- Redis 7+
- Milvus 2.5+（可选，向量检索）

### 1.2 后端启动

```bash
git clone <repo>
cd kb_mp

# 安装依赖（推荐 uv）
uv sync --all-extras

# 配置环境变量
cp .env.example .env
# 编辑 .env 中的 DATABASE_URL / REDIS_URL

# 初始化数据库
uv run alembic upgrade head
uv run python scripts/seed.py --reset

# 启动
uv run uvicorn app.api.app:app --reload --port 8000
```

### 1.3 前端启动

```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
```

## 二、生产部署（Docker Compose）

### 2.1 单机部署

```bash
cd deploy
docker compose up -d
```

启动后访问 `http://<host>:8000`。

### 2.2 服务清单

| 服务 | 端口 | 镜像 |
|---|---|---|
| kb_mp_app | 8000 | ghcr.io/<org>/kb_mp:latest |
| mysql | 3306 | mysql:8.0 |
| redis | 6379 | redis:7-alpine |
| milvus | 19530 | milvusdb/milvus:v2.5.4 |
| etcd | 2379 | quay.io/coreos/etcd |
| minio | 9000 | minio/minio |

## 三、生产环境变量

生产部署必须覆盖以下 `.env`：

```ini
DEBUG=false
JWT_SECRET=<random-32-bytes>
DATABASE_URL=mysql+aiomysql://<user>:<pass>@<host>:3306/kb_mp
REDIS_URL=redis://<host>:6379/0
EMBEDDING_BACKEND=remote_openai
OPENAI_API_KEY=<secret>
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus
MILVUS_URL=http://<host>:19530
```

## 四、CICD

GitHub Actions 自动触发：

- **CI**（push/PR）：ruff format + lint + pytest（87 主用例）
- **CD**（push master）：docker build + push 到 `ghcr.io/<org>/kb_mp`

详见 `.github/workflows/`。

## 五、运维检查清单

- [ ] MySQL 慢日志开启
- [ ] Redis 内存监控（建议 < 70%）
- [ ] Milvus 索引健康（curl http://host:9091/healthz）
- [ ] 后端日志轮转（logrotate）
- [ ] JWT_SECRET 32 字节以上且定期轮换