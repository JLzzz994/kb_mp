# Spec 总索引

> 模块级 SPEC 文档集，遵循 [python-spec-skill](C:/Users/Administrator/.agents/skills/python-spec-skill/SKILL.md) 方法论，可直接编码。

---

## 目录

| 模块 | Spec | 阶段 | 状态 |
| --- | --- | --- | --- |
| M1 | [认证鉴权](./M1-认证鉴权.md) | P0 | ✅ |
| M2 | [组织架构管理](./M2-组织架构管理.md) | P0 | ✅ |
| M3 | [知识资产管理](./M3-知识资产管理.md) | P1 | ✅ |
| M4 | [AI 对话工作台](./M4-AI对话工作台.md) | P2 | ✅ |
| M5 | [数据看板](./M5-数据看板.md) | P3 | ✅ |
| M6 | [知识沉淀管理](./M6-知识沉淀管理.md) | P4 | ✅ |

---

## 1. 模块依赖关系

```
                  ┌─────────────┐
                  │    M1 认证  │
                  │   鉴权基座  │
                  └──────┬──────┘
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌────────┐  ┌────────┐  ┌────────┐
        │  M2   │  │  M3   │  │  M4   │
        │ 组织  │  │ 知识  │  │  AI  │
        └────┬─┘  └───┬────┘  └───┬────┘
             │         │           │
             │   ┌─────┴─────┐     │
             └──►│  M5 看板  │◄────┘
                 │ qa_logs  │
                 └─────┬─────┘
                       │
                  ┌────▼────┐
                  │  M6   │
                  │ 沉淀  │
                  └────────┘
```

### 1.1 上下游矩阵

| 模块 | 上游 | 下游 |
| --- | --- | --- |
| M1 | 无 | M2 / M3 / M4 / M5 / M6 |
| M2 | M1 | M3 / M4 |
| M3 | M1 / M2 | M4 / M5 / M6 |
| M4 | M1 / M3 | M5 / M6 |
| M5 | M4 | 无 |
| M6 | M4 / M3 | 无 |

### 1.2 共享接口

| 接口 | 定义模块 | 调用模块 |
| --- | --- | --- |
| `POST /api/v1/knowledge/check-permissions` | **M3** | M4（LangGraph permission_filter） |
| `GET /api/v1/org/users/{id}` | M2 | M3（creator 校验）/ M4（user info） |
| `GET /api/v1/auth/me` | M1 | 全部模块（前端），其他模块也用 `CurrentUserDep` 后端依赖 |

### 1.3 共享数据对象

| 表 | 写入模块 | 读取模块 |
| --- | --- | --- |
| `users` | M2 | M1 / M3 / M4 / M5 / M6 |
| `knowledge_units` | M3 | M4 / M5 / M6 |
| `qa_access_logs` | M4 | M5 / M6 |
| `chat_sessions` | M4 | M4 |
| `faqs` | M6 | M4（缓存命中） |

---

## 2. 接口清单汇总

按模块分组，详细见各 Spec §7。

| 模块 | Method | 路径 | 权限 | 来源 |
| --- | --- | --- | --- | --- |
| M1 | POST | `/api/v1/auth/login` | 公开 | M1 §7.1 |
| M1 | GET | `/api/v1/auth/me` | 需登录 | M1 §7.2 |
| M1 | POST | `/api/v1/auth/logout` | 需登录 | M1 §7.3 |
| M2 | GET | `/api/v1/org/departments` | `dept:read` | M2 §7 |
| M2 | POST | `/api/v1/org/departments` | `dept:write` | M2 §7 |
| M2 | PUT | `/api/v1/org/departments/{id}` | `dept:write` | M2 §7 |
| M2 | DELETE | `/api/v1/org/departments/{id}` | `dept:write` | M2 §7 |
| M2 | GET | `/api/v1/org/users` | `user:read` | M2 §7 |
| M2 | GET | `/api/v1/org/users/{id}` | `user:read` | M2 §7 |
| M2 | POST | `/api/v1/org/users` | `user:write` | M2 §7 |
| M2 | PUT | `/api/v1/org/users/{id}` | `user:write` | M2 §7 |
| M2 | PATCH | `/api/v1/org/users/{id}/status` | `user:write` | M2 §7 |
| M2 | POST | `/api/v1/org/users/{id}/reset-password` | `user:write` | M2 §7 |
| M2 | GET | `/api/v1/org/roles` | `role:read` | M2 §7 |
| M2 | POST | `/api/v1/org/roles/{id}/permissions` | `role:write` | M2 §7 |
| M2 | GET | `/api/v1/org/permissions` | `role:read` | M2 §7 |
| M3 | POST | `/api/v1/knowledge/import` | `knowledge:write` | M3 §7.2 |
| M3 | GET | `/api/v1/knowledge-units` | `knowledge:read` | M3 §7 |
| M3 | GET | `/api/v1/knowledge-units/{id}` | `knowledge:read` | M3 §7 |
| M3 | PATCH | `/api/v1/knowledge-units/{id}` | `knowledge:write` | M3 §7 |
| M3 | DELETE | `/api/v1/knowledge-units` | `knowledge:delete` | M3 §7 |
| M3 | POST | `/api/v1/knowledge-units/{id}/permissions` | `knowledge:write` | M3 §7 |
| M3 | **POST** | **`/api/v1/knowledge/check-permissions`** | **需登录** | **M3 §7.1（共享）** |
| M4 | POST | `/api/v1/ai/sessions` | `ai:chat` | M4 §7 |
| M4 | GET | `/api/v1/ai/sessions` | `ai:chat` | M4 §7 |
| M4 | GET | `/api/v1/ai/sessions/{id}` | `ai:chat` | M4 §7 |
| M4 | PATCH | `/api/v1/ai/sessions/{id}` | `ai:chat` | M4 §7 |
| M4 | DELETE | `/api/v1/ai/sessions/{id}` | `ai:chat` | M4 §7 |
| M4 | **POST** | **`/api/v1/ai/chat/stream`** | `ai:chat` | M4 §7.1（SSE） |
| M4 | POST | `/api/v1/ai/chat/resume` | `ai:chat` | M4 §7.2 |
| M5 | GET | `/api/v1/dashboard/metrics` | `dashboard:read` | M5 §7.1 |
| M5 | GET | `/api/v1/dashboard/rankings/questions` | `dashboard:read` | M5 §7 |
| M5 | GET | `/api/v1/dashboard/rankings/units` | `dashboard:read` | M5 §7.2 |
| M5 | GET | `/api/v1/dashboard/stats/tokens` | `dashboard:read` | M5 §7 |
| M5 | GET | `/api/v1/dashboard/stats/response-time` | `dashboard:read` | M5 §7 |
| M6 | GET | `/api/v1/faqs` | `faq:read` | M6 §7 |
| M6 | GET | `/api/v1/faqs/recommendations` | `faq:read` | M6 §7 |
| M6 | POST | `/api/v1/faqs` | `faq:write` | M6 §7 |
| M6 | PATCH | `/api/v1/faqs/{id}` | `faq:write` | M6 §7 |
| M6 | POST | `/api/v1/faqs/{id}/review` | `faq:review` | M6 §7.1 |
| M6 | DELETE | `/api/v1/faqs/{id}` | `faq:write` | M6 §7 |
| M6 | GET | `/api/v1/knowledge-gaps` | `gap:read` | M6 §7 |
| M6 | POST | `/api/v1/knowledge-gaps/{id}/create-unit` | `knowledge:write` | M6 §7.2 |

**接口总数**：43 个（M1: 3 / M2: 13 / M3: 7 / M4: 7 / M5: 5 / M6: 8）

---

## 3. 数据对象清单汇总

11 张表（详见《数据对象文档》），按 Spe c 写入归属：

| 表 | 主写入模块 | 字段新增 |
| --- | --- | --- |
| users | M2 | — |
| departments | M2 | — |
| roles | M2 | — |
| user_roles | M2 | — |
| role_permissions | M2 | — |
| knowledge_units | M3 | `content_hash` |
| unit_permissions | M3 | — |
| qa_access_logs | M4 | — |
| chat_sessions | M4 | — |
| faqs | M6 | `unit_updated_at_snapshot` |
| knowledge_gaps | M6 | — |

---

## 4. 阶段映射

| 阶段 | 包含模块 | 前置门禁 |
| --- | --- | --- |
| **P0** | M1 + M2 | 登录 + 用户/角色/部门 CRUD + RBAC 通过门禁 |
| **P1** | M3 | 知识导入 + 权限配置 + `check-permissions` 通过 |
| **P2** | M4 | Milvus 集成 + LangGraph 8 节点 + SSE 端到端 |
| **P3** | M5 | 看板 5 项指标 + TOP 榜 + 趋势图 |
| **P4** | M6 | FAQ 闭环 + 缺口识别 + 一键建档 |
| **P5** | 前端 6 模块 | 演示链路完整 |

每阶段结束：
1. 跑 `uv run ruff format --check . && uv run ruff check . && uv run pytest`
2. 跑 `uv run alembic upgrade head` 迁移
3. 跑该模块 Spec §10 测试用例
4. 必要时更新 `docs/概要设计总纲.md` 阶段状态

---

## 5. 关键设计决策（贯穿所有 Spec）

| 决策 | 描述 | 出处 |
| --- | --- | --- |
| LangGraph 8 节点 | faq → retrieve → rerank → permission_filter → interrupt? → assemble → generate → record | 概要设计 §5.2 + ADR-0002 |
| 鉴权算法 | 用户权限位图 + 内存 OR 集合运算 | 概要设计 §5.2 + M3 §5.6 |
| FAQ 缓存 | Redis HSET + 单元版本校验 | 概要设计 §5.3 + M6 §5.3 |
| 文档切片 | 保护块占位符 + RecursiveCharacterTextSplitter | 概要设计 §5.1 + M3 §5.4 |
| 文档去重 | SHA-256(content) UNIQUE | 概要设计 §5.1 + M3 §4.1 |
| 鉴权接口 | M3 定义、M4 共享 | M3 §7.1 |
| SSE 事件 | 8 类：ready/progress/delta/citation/unauthorized/interrupt/final/error | 接口约定 §6.1 + M4 §7.1 |
| 多轮会话 | chat_sessions.history_json 含 slots / pending_turn | 数据对象 §4.2 + M4 §4.1 |
| 历史窗口 | 6 轮，trim_messages 控制 | M4 §5.5 |
| 动态断崖 | GAP_RATIO=0.75 / MIN=1 / MAX=10 | M4 §5.5 |

---

## 6. 外部依赖清单

| 依赖 | 用途 | 涉及模块 | 配置 |
| --- | --- | --- | --- |
| MySQL 8 | 主数据库 | M1-M6 | `settings.database_url` |
| Redis 7 | 鉴权位图 + FAQ 缓存 + 临时状态 | M1 + M3 + M4 + M6 | `settings.redis_url` |
| Milvus 2.4 | 向量检索 | M3 + M4 | `settings.milvus_host/port` |
| OpenAI API | LLM + Embedding | M3 + M4 + M6 | `settings.openai_api_key/base_url/model` |
| APScheduler | FAQ 挖掘定时 | M6 | `app/infrastructure/scheduler.py` |
| LangGraph 1.2 | AI 流编排 | M4 | `langgraph` extras |
| pypdf / python-docx / markdown-it | 文档解析 | M3 | 详见 pyproject.toml |
| bcrypt | 密码哈希 | M1 + M2 | `settings.password_bcrypt_cost` |

---

## 7. 文档结构与生成约定

每份 Spec 遵循 [python-spec-skill](C:/Users/Administrator/.agents/skills/python-spec-skill/SKILL.md) 11 章节结构：

1. 文档说明 / 范围 / 依据 / 非目标
2. 模块概览与上下游依赖
3. 精确目录与文件清单
4. 数据对象与迁移
5. 后端设计（Router / Service / Repository / Domain / 异常）
6. 前端设计（页面 / 组件 / 状态 / API 方法）
7. OpenAPI 接口契约
8. 异步与适配器
9. 权限、审计与日志
10. 测试与验收
11. 待确认项

**生成 method**（grill-with-docs）：
- Phase 1：grilling 对齐关键决策（树状分支问题）
- Phase 2：domain-modeling 巩固领域词汇（来自 `docs/CONTEXT.md`）
- Phase 3：按 SPEC 11 章节模板生成

**下游使用**：
- TDD：`tests/test_<module>.py` 直接参照 Spec §5 + §10
- 实施计划：调用 `writing-plans` 时必须引用本 Spec 真实文件路径
- Review：调用 `code-review` 时以 SPEC §5/§7 为符合性标准

---

## 8. 验收门禁

每个模块完成时必须通过：

```bash
# 1. 数据库迁移
uv run alembic upgrade head

# 2. 后端格式 / lint / 测试
uv run ruff format --check .
uv run ruff check .
uv run pytest

# 3. OpenAPI 生成
uv run python -c "from app.api.app import app; import json; print(len(app.routes))"  # 应等于表 §2 接口数

# 4. 模块特定测试
uv run pytest tests/test_<module>.py -v

# 5. 端到端冒烟（按演示链路）
# 参考 docs/原型设计 §7 核心演示链路
```

完整端到端演示链路见 `docs/原型设计 §7`，按 P0→P5 顺序逐阶段跑通。

---

## 9. 与上层文档追溯

| 本 README 章节 | 上层文档 |
| --- | --- |
| §1 模块依赖 | 概要设计 §6 关键技术决策 |
| §2 接口清单 | 接口约定 §7 接口分组清单 |
| §3 数据对象 | 数据对象 §1 总览 |
| §4 阶段映射 | 概要设计 §10 阶段与里程碑 |
| §5 关键决策 | 概要设计 §6 决策表 |
| §6 外部依赖 | 概要设计 §2 技术选型 + 部署 |

---

## 附录 A：当前 Spec 完成度

- ✅ M1 — 认证鉴权（440 + 行）
- ✅ M2 — 组织架构管理（240 行）
- ✅ M3 — 知识资产管理（320 行）
- ✅ M4 — AI 对话工作台（470 行）
- ✅ M5 — 数据看板（200 行）
- ✅ M6 — 知识沉淀管理（320 行）
- ✅ README（本文件）

**总计**：约 2000 行模块级 SPEC。

**下一阶段**：按 P0 启动 M1 + M2 编码；从 `tests/test_auth_login.py` 起按 TDD 推进。