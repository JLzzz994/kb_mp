# kb_mp 交付物

企业级 AI 知识库管理平台（kb_mp）完整交付包。

## 一、目录结构

```
交付物/
├── 01-启动脚本/           # 一键启动 + 后端/前端分离启动 + 部署运维手册
├── 02-数据库初始化/       # SQL schema + Alembic 初始化 + README
├── 03-示例数据/           # 4 份 Markdown 演示文档 + FAQ + seed JSON
├── 04-接口文档/           # 43 端点接口清单 + 鉴权权限说明 + SSE 事件约定
├── 05-演示链路/           # curl 演示脚本 + 完整演示步骤 + 流程图
├── 06-已编译前端/         # Vite 编译产物 + 部署说明
└── README.md              # 本文件（总入口）
```

## 二、交付物清单

| # | 类别 | 数量/规格 | 用途 |
|---|------|---------|------|
| 01 | 启动脚本 | 6 个 bat/sh | 一键启动 / 后端 / 前端 / 部署手册 |
| 02 | 数据库初始化 | 4 文件 | schema.sql + init_db.sh + init_db.bat + README |
| 03 | 示例数据 | 6 文�� | 4 份 Markdown + 1 FAQ + 1 seed JSON + README |
| 04 | 接口文档 | 3 文件 | 接口清单 + 鉴权权限 + SSE 事件约定 |
| 05 | 演示链路 | 2 文件 | curl 演示脚本 + 完整步骤说明 |
| 06 | 已编译前端 | 2 MB | index.html + assets/ + README |

## 三、快速启动（5 分钟跑通）

### 0. 前置依赖

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.12+ | 后端 |
| Node.js | 18+ | 前端开发 |
| MySQL | 8.0+ | 主数据 |
| Redis | 7+ | 鉴权位图 + FAQ 缓存 |
| Milvus | 2.5+ | 向量检索（可选） |
| uv | 0.4+ | Python 包管理（推荐） |

### 1. 启动后端

```bash
cd 交付物/01-启动脚本
bash 启动后端.sh        # macOS / Linux
一键启动-backend.bat    # Windows
```

**自动完成**：
- 同步依赖（`uv sync --all-extras`）
- 初始化数据库（Alembic migration + seed）
- 启动 uvicorn :8000

### 2. 启动前端

```bash
cd 交付物/01-启动脚本
bash 启动前端.sh         # macOS / Linux
一键启动-frontend.bat    # Windows
```

**自动完成**：
- `npm install`
- `npm run dev`（vite :5173 + API proxy → :8000）

### 3. 一键演示

```bash
cd 交付物/05-演示链路
bash demo_curl.sh
```

完整跑通鉴权 + 知识导入 + AI 问答 + 看板 + FAQ 全���路。

## 四、关键路径

| 资源 | 路径 |
|------|------|
| 后端 API | http://localhost:8000/api/v1 |
| Swagger UI | http://localhost:8000/docs |
| 前端 dev | http://localhost:5173 |
| 前端 dist | `交付物/06-已编译前端/` |
| 演示账号 | `admin / Admin@123` |

## 五、依赖与依赖矩阵

### 演示最小集（MySQL + Redis + 模拟 LLM/Embedding/Milvus）

```bash
# 启动 MySQL + Redis（Docker）
docker run -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=kb_mp mysql:8.0
docker run -d -p 6379:6379 redis:7-alpine

# .env 中 LLM/Embedding/Milvus 留空或 mock
OPENAI_API_KEY=                  # 留空
EMBEDDING_BACKEND=mock           # 演示模式
MILVUS_URL=                       # 留空 → 触发 mock 召回
```

启动后 AI 问答仍可工作（fallback 到 DB 关键字检索 + 简单 prompt 拼接）。

### 生产完整集（本地 BGE-M3 + 远程 DashScope + 远程 Milvus）

```ini
EMBEDDING_BACKEND=local_bge
BGE_M3_PATH=D:/ai_models/modelscope_cache/models/BAAI/bge-m3
EMBEDDING_DIM=1024

EMBEDDING_BACKEND=remote_openai  # 或双适配
OPENAI_API_KEY=<secret>
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus

MILVUS_URL=http://<host>:19530
MILVUS_COLLECTION=kb_units
```

## 六、模块化拆解

### M1：认证鉴权
- bcrypt cost=12 密码哈希
- JWT HS256（8h 过期）
- 17 权限码 + Redis bitmap 缓存
- 鉴权位图 5 分钟 TTL
- 详见 `04-接口文档/鉴权与权限.md`

### M2：组织架构
- 部门树（parent_id 自引用）
- 用户 CRUD + 重置密码
- 角色 + 权限码分配
- 详见 `04-接口文档/接口清单.md §3`

### M3：知识资产
- 知识单元 CRUD
- 四维权限（global / department / role / user）
- 多文件上传 + 自动切片
- SHA-256 去重
- check-permissions 鉴权接口
- 详见 `04-接口文档/接口清单.md §4`

### M4：AI 对话
- LangGraph 8 节点编排
- SSE 8 事件流
- 多轮会话（chat_sessions 表）
- 中断恢复机制
- 详见 `04-接口文档/SSE事件约定.md`

### M5：数据看板
- 5 端点（metrics / rankings ×2 / stats ×2）
- 24h / 7d / 30d / 90d 时间桶
- SQL 实时聚合
- 详见 `04-接口文档/接口清单.md §6`

### M6：知识沉淀
- FAQ CRUD + 审核
- Redis 缓存同步
- 知识缺口识别（一键建档）
- 详见 `04-接口文档/接口清单.md §7`

## 七、测试覆盖

90 个 pytest 用例全绿（87 主用例 + 3 e2e）：

| 模块 | 用例 |
|------|------|
| M1 鉴权 | 18 |
| M2 组织 | 14 |
| M3 知识 | 22 |
| M4 AI | 15 |
| M5 看板 | 8 |
| M6 沉淀 | 13 |
| M7 真实接入 | 3 e2e |

## 八、CICD

GitHub Actions 完整接入：

- **CI**（`.github/workflows/ci.yml`）：ruff format/lint + pytest
- **CD**（`.github/workflows/cd.yml`）：docker build + push GHCR
- **Dependabot**（`.github/dependabot.yml`）：周级依赖更新

详见根目录 `README.md` §CI/CD。

## 九、常见问题

| Q | A |
|---|---|
| 8000 端口被占用？ | 改 `main.py` 的 port，或停占端口进程 |
| 401 未授权？ | JWT 过期 / Redis 不可达 / 用户被禁用 |
| 403 无权限？ | 当前用户缺少对应 `permission_code` |
| AI 召回为空？ | 检查知识权限 + Milvus 数据 + 嵌入向量模型 |
| SSE 连接断？ | 客户端需支持 EventSource；改用 fetch + ReadableStream |
| bcrypt 慢？ | cost=12 默认；演示期可降至 cost=10 |

## 十、验证清单

启动后必跑一遍：

- [ ] `curl http://localhost:8000/api/v1/health` 返回 `{"status": "ok"}`
- [ ] 登录 admin 获取 token
- [ ] 上传 1 个 Markdown 文件 → 看到 accepted_count=1
- [ ] AI 问答 "kb_mp 是什么？" → 收到 SSE 流 + final 事件
- [ ] 数据看板 metrics 返回 200
- [ ] 浏览器访问 http://localhost:5173 → 登录页可渲染

## 十一、版本

- kb_mp 版本：0.1.0
- 交付日期：2026-08-19
- 测试覆盖：90 用例绿
- 技术栈：FastAPI + React + LangGraph + MySQL + Redis + Milvus