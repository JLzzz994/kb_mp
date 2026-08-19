# kb_mp — 企业知识库管理平台

## 项目简介

kb_mp（Knowledge Base Management Platform）是一个面向企业内部知识资产管理的 AI 平台。
核心能力：文档智能解析、向量语义检索、AI 鉴权问答、数据看板、FAQ 沉淀管理。

## 文档导航

- `docs/specs/` — 6 大模块 Spec（M1-M6）
- `docs/impl/` — 实现蓝图（IMPL-M1-M6）
- `docs/adr/` — 架构决策记录
- `app/` — 后端代码（FastAPI + SQLAlchemy + LangGraph 8 节点）
- `frontend/` — 前端代码（Vue 3 + Vite + TypeScript）
- `deploy/` — Docker Compose 部署
- `tests/` — pytest 测试套件（90 用例）

## 本地开发

```bash
# 后端
uv sync --all-extras
uv run uvicorn app.api.app:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev
# → http://127.0.0.1:5173
```

## 部署

```bash
cd deploy
docker compose up -d
# → kb_mp_app 监听 8000，mysql/redis/etcd/minio 同栈
```

## CI/CD

### 启用步骤

1. **创建 GitHub 仓库**：
   ```bash
   git init && git remote add origin git@github.com:<user>/kb_mp.git
   git add -A && git commit -m "init" && git push -u origin master
   ```
2. **GitHub Actions 自动启用**：push 后 `ci.yml`（ruff + pytest）和 `cd.yml`（docker build + push GHCR）触发
3. **Dependabot 自动 PR**：每周检查 `uv.lock` 和 `frontend/package-lock.json` 更新

### Workflows

- `.github/workflows/ci.yml` — push/PR 触发，跑 ruff format/lint + pytest（87 用例 + 演示用 mock）
- `.github/workflows/cd.yml` — push 到 master 自动构建 + push Docker 镜像到 `ghcr.io/<user>/kb_mp`
- `.github/dependabot.yml` — 周级依赖更新

### 本地模拟 CI

```bash
# ruff + pytest
uv run ruff format --check .
uv run ruff check .
uv run pytest -v --ignore=tests/test_e2e_t7_real_vectorize.py
```

### 权限要求

- `Settings → Actions → General → Workflow permissions → Read and write permissions`
- GHCR 推送需 `packages: write`（默认满足）

## 测试矩阵

| 模块 | 用例数 | 覆盖 |
|------|--------|------|
| M1 鉴权 | 18 | login/me/logout/2 状态 + 8 权限码 |
| M2 组织 | 14 | 部门树 + 用户/角色 CRUD |
| M3 知识 | 22 | CRUD + import 7 + check-permissions + 真实接入 e2e |
| M4 AI | 15 | 8 节点 LangGraph + SSE 8 事件 + chat_session |
| M5 看板 | 8 | 5 端点 + 趋势分桶 |
| M6 沉淀 | 13 | FAQ + 缓存 + 缺口识别 |

总计 **90 用例**。
