# IMPL 总索引

> 模块级 Python 实现蓝图，含完整方法级伪代码（中文注释）+ 完整 pytest 用例。可直接照写编码。

---

## 目录

| 模块 | IMPL | 阶段 | 关键特性 |
| --- | --- | --- | --- |
| M1 | [认证鉴权](./IMPL-M1-认证鉴权.md) | P0 | bcrypt + JWT (HS256) + Redis 鉴权位图 |
| M2 | [组织架构管理](./IMPL-M2-组织架构管理.md) | P0 | 部门树 + 用户/角色 CRUD + 权限变更批量失效 |
| M3 | [知识资产管理](./IMPL-M3-知识资产管理.md) | P1 | ParserFactory + Splitter 保护块 + SHA-256 幂等 + check-permissions |
| M4 | [AI 对话工作台](./IMPL-M4-AI对话工作台.md) | P2 | LangGraph 8 节点 + SSE 8 事件 + interrupt/resume |
| M5 | [数据看板](./IMPL-M5-数据看板.md) | P3 | 5 项指标 + TOP 榜 + 趋势图（MySQL 聚合）|
| M6 | [知识沉淀管理](./IMPL-M6-知识沉淀管理.md) | P4 | FAQ 审核 + Redis 缓存同步 + APScheduler + 缺口识��� |

---

## 1. 跨模块数据流

```
M1 JWT Token + CurrentUser
   │
   ▼
M2 创建 User/Role/Department，权限变更触发 Redis 位图失效
   │
   ▼
M3 知识导入（SHA-256 去重 + 解析切片 + 入库 + 向量化）
   │
   ▼
M3 check-permissions → 用户权限位图 → Redis 缓存
   │
   ▼
M4 LangGraph 8 节点：faq → retrieve → rerank → permission_filter
                    → interrupt? → assemble → generate → record_log
   │
   ▼
M5 qa_access_logs 聚合 → 看板指标
   │
   ▼
M6 每日 02:00 APScheduler → 挖掘 FAQ
   ▼
M6 知识缺口识别 → 一键建档 → 回 M3
```

---

## 2. 测试矩阵

按模块汇总 pytest 用例数：

| 模块 | 用例数 | 覆盖重点 |
| --- | --- | --- |
| M1 | 17 | 登录 3 状态、me 4 状态、Token 签发/校验、RBAC 拦截、Redis 位图失效 |
| M2 | 13 | 部门树、删除保护、用户密码哈希、用户名冲突、位图失效、权限批量失效 |
| M3 | 12 | 4 格式解析、UTF-8/GBK 切换、代码块保护、SHA-256 去重、文件大小、check-permissions 拆分 |
| M4 | 14 | 8 节点编排、SSE 8 事件、FAQ 命中、interrupt、resume、rerank 动态断崖 |
| M5 | 8 | 5 项指标、range 校验、TOP 排序、去重、按日分桶、空���据 |
| M6 | 12 | 审核 + Redis 同步、版本失效、自动挖掘、idempotent、阈值触发、一键建档 |
| **合计** | **~76** | 全模块端到端 + 单元 + 集成 |

---

## 3. 关键代码片段索引

| 模块 | 关键方法 | IMPL 位置 |
| --- | --- | --- |
| M1 | `AuthService.login` / `load_current_user` / `me` | [IMPL-M1 §2.3](./IMPL-M1-认证鉴权.md) |
| M1 | `JWTIssuer.issue` /`verify` | [IMPL-M1 §2.4](./IMPL-M1-认证鉴权.md) |
| M2 | `DepartmentService.list_tree`（内存组装树） | [IMPL-M2 §2](./IMPL-M2-组织架构管理.md) |
| M2 | `RoleService.assign_permissions`（批量失效） | [IMPL-M2 §4](./IMPL-M2-组织架构管理.md) |
| M3 | `ParserFactory.parse`（Format-Handler-Map） | [IMPL-M3 §2](./IMPL-M3-知识资产管理.md) |
| M3 | `Splitter.split`（保护块占位符法） | [IMPL-M3 §3](./IMPL-M3-知识资产管理.md) |
| M3 | `KnowledgeImportService.import_files` | [IMPL-M3 §4](./IMPL-M3-知识资产管理.md) |
| M3 | `KnowledgeUnitService.create`（手动 + 一键建档） | [IMPL-M3 §6](./IMPL-M3-知识资产管理.md) |
| M3 | `KnowledgeUnitRepository.get_updated_at` / `list_content_for_ids` | [IMPL-M3 §5](./IMPL-M3-知识资产管理.md) |
| M3 | `KnowledgePermissionService.compute_user_permission_bitmap_sync`（纯函数 OR） | [IMPL-M3 §7](./IMPL-M3-知识资产管理.md) |
| M4 | `faq_cache_lookup` / `rerank` / `permission_filter` / `interrupt_node` / `agent | [IMPL-M4 §3](./IMPL-M4-AI对话工作台.md) |
| M4 | `AIService.chat_stream`（SSE 编排） | [IMPL-M4 §5](./IMPL-M4-AI对话工作台.md) |
| M5 | `DashboardRepository.fetch_metrics` / `fetch_unit_rankings`（JSON 展开） | [IMPL-M5 §2](./IMPL-M5-数据看板.md) |
| M6 | `FaqCacheService.get`（版本校验） | [IMPL-M6 §2](./IMPL-M6-知识沉淀管理.md) |
| M6 | `FaqMiningService.run`（APScheduler 任务） | [IMPL-M6 §6](./IMPL-M6-知识沉淀管理.md) |
| M6 | `KnowledgeGapService.one_click_create_unit`（建档闭环） | [IMPL-M6 §5](./IMPL-M6-知识沉淀管理.md) |

---

## 4. 门禁验证脚本

每个模块完成后跑：

```bash
# 1. 格式
uv run ruff format --check .

# 2. Lint
uv run ruff check .

# 3. 模块单测
uv run pytest tests/test_<module>.py -v --cov=app.services.<module>_service --cov-report=term-missing

# 4. 整体回归
uv run pytest -v

# 5. 端到端演示（按 docs/原型设计 §7 链路）
```

---

## 5. 关键依赖与版本约束

| 依赖 | 版本 | 用途 | 涉及模块 |
| --- | --- | --- | --- |
| fastapi | 0.136.3 | 路由 | 全部 |
| sqlalchemy | 2.0.50 | ORM async | M1~M6 |
| aiomysql | 0.3.2 | MySQL 异步驱动 | 全部 |
| langchain | 1.3.10 | LLM 抽象 | M4 + M6 |
| langgraph | 1.2.6 | 图编排 | M4 |
| pymilvus | ≥2.6 | Milvus gRPC 客户端 | M3 + M4 |
| langchain-milvus | latest | LangChain Milvus 集成（pymilvus 客户端封装） | M3 + M4 |
| redis | ≥5.0 | async client | M1 + M3 + M4 + M6 |
| pypdf | latest | PDF 解析 | M3 |
| python-docx | latest | Word 解析 | M3 |
| markdown-it | latest | MD 解析 | M3 |
| langchain-text-splitters | latest | RecursiveTextSplitter | M3 |
| apscheduler | 3.x | 定时任务 | M6 |
| bcrypt | latest | 密码哈希 | M1 + M2 |
| PyJWT | latest | JWT | M1 |

---

## 6. IMPL 与上层文档关系

| 上层文档 | 关系 |
| --- | --- |
| [PRD V1.0](../知识库管理平台PRD.md) | 业务背景 |
| [概要设计总纲 V1.0](../概要设计总纲.md) | 技术选型 + 关键决策 |
| [数据对象文档 V1.0](../数据对象文档.md) | 数据模型 |
| [接口约定文档 V1.0](../接口约定文档.md) | OpenAPI 契约 |
| [原型设计说明 V1.0](../知识库管理平台原型设计说明.md) | 视觉规范 + 页面清单 |
| [原型实施计划 V1.0](../知识库管理平台原型实施计划.md) | 前端任务分解 |
| [Spec M1~M6](../specs/) | 模块级 SPEC（数据对象 + 接口 + 测试用例） |
| IMPL（本目录） | 方法级伪代码 + 完整 pytest |

---

## 7. 实施节奏建议

| 阶段 | 任务 | 预计文件 |
| --- | --- | --- |
| P0 启动 | M1 `tests/test_auth_login.py` 起手 → 跑红 → 实现 AuthService → 跑绿 | ~15 个文件 |
| P0 续 | M2 用户/角色/部门 → 跑绿 | ~18 个文件 |
| P1 | M3 ParserFactory + Splitter + 导入 → 鉴权接口 | ~22 个文件 |
| P2 | M4 LangGraph 8 节点 + SSE + 多轮 | ~20 个文件 |
| P3 | M5 5 项指标聚合 | ~6 个文件 |
| P4 | M6 FAQ 审核 + APScheduler + 缺口 | ~16 个文件 |

每阶段结束更新 `docs/概要设计总纲.md` §10 阶段状态 + 写对应 ADR（如引入新依赖）。

---

## 8. 验收 Checklist（合并各模块）

按 Spec §10 与 IMPL §5/§6/§10 各模块 checklist 合并，约 80 条；通过 `pytest --tb=short` 与 `coverage report` 一键校验。