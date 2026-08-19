# 知识库管理平台 PRD（产品需求文档）

| 项目 | 内容 |
| --- | --- |
| 文档版本 | V1.0 |
| 编写日期 | 2026-08-18 |
| 文档状态 | 待评审 |
| 文档来源 | 基于《知识库管理平台需求.md》转化 |
| 交付范围 | 前端应用 + 后端服务 + 数据库初始化脚本 + 示例知识文档 + 接口文档 + 业务演示链路 |

---

## 1. 项目概述

### 1.1 项目目标

构建一个集 **知识维护、多维权限管理、AI 问答鉴权检索、数据看板、知识自动沉淀** 于一体的企业级知识库管理平台。核心价值：

- **知识资产化**：单篇与批量导入文档，自动拆分为独立知识单元并向量化存储。
- **权限精细化**：基于 RBAC 的操作权限 + 四维（全局/部门/角色/个人）混合数据权限。
- **AI 安全化**：智能体问答强制鉴权召回，无权限知识单元明确提示，杜绝越权。
- **运营数据化**：访问量、热度榜、Token 消耗、响应时长等指标可视化。
- **知识自循环**：高频问题自动推荐 FAQ 沉淀、低置信度提问形成知识缺口清单。

### 1.2 交付物清单

1. 前端 SPA（Vue3 + Element Plus + ECharts）
2. 后端服务（FastAPI + SQLAlchemy 异步）
3. MySQL 数据库初始化脚本与种子数据
4. 示例知识文档（PDF / Markdown / Word / TXT）
5. 接口说明文档（OpenAPI / Swagger）
6. 端到端业务演示链路（用户登录→知识导入→权限配置→AI 问答→看板→FAQ 沉淀）

---

## 2. 用户角色与权限模型

### 2.1 角色定义

| 角色 | 操作权限范围 | 业务职责 |
| --- | --- | --- |
| **系统管理员** | 用户/角色/部门 CRUD、菜单与按钮权限分配、看板查看、AI 访问 | 维护组织架构、分配权限、监控系统运行 |
| **知识管理员** | 知识导入、CRUD、删除、数据权限配置、FAQ 审核发布、缺口维护 | 管理知识资产、审核 FAQ、补全知识缺口 |
| **普通用户 / 提问者** | AI 问答访问、查看个人中心 | 登录后进行 AI 智能问答，按个人数据权限获取回答 |

### 2.2 权限分层

```
操作权限（功能层）   =  菜单可见性 + 按钮可用性 + 路由拦截
数据权限（资源层）   =  global ∪ department ∪ role ∪ user  (OR 逻辑)
登录态（鉴权层）     =  JWT Token 校验，过期/失效强制重登
```

### 2.3 数据权限核心规则

- **默认拒绝**：知识单元在未被显式分配权限前，对任何用户均不可访问。
- **四类实体**：全局（global）、部门（department）、角色（role）、个人（user）。
- **OR 匹配**：用户只要满足其中**任意一种**实体匹配即可访问该知识单元。
- **混合分配**：单一知识单元可同时分配多类多实体权限（如"研发部 + 管理员角色 + 用户张三"）。

---

## 3. 功能需求

### 3.1 认证与个人中心

| 需求编号 | 功能点 | 详细描述 |
| --- | --- | --- |
| F-AUTH-01 | 用户名密码登录 | 校验通过返回 JWT Token，包含 user_info（ID、用户名、显示名、部门、角色列表、操作权限码）和 permissions |
| F-AUTH-02 | 登录态维持 | Token 写入前端存储，路由守卫校验失效自动跳转登录页 |
| F-AUTH-03 | 个人中心 | 展示当前用户身份、所属部门、拥有角色、登录时间 |

### 3.2 组织架构管理

| 需求编号 | 功能点 | 详细描述 |
| --- | --- | --- |
| F-ORG-01 | 部门管理 | 树形结构维护：新增/编辑/删除部门，指定负责人（leader_id），设置排序 |
| F-ORG-02 | 用户管理 | 列表展示用户名、显示名、部门、角色、状态；支持新增、编辑、重置密码、启停用 |
| F-ORG-03 | 角色管理 | 维护角色名称、角色编码、操作权限树勾选（增/删/改/查/AI访问） |
| F-ORG-04 | 菜单/按钮权限 | 操作权限树按权限码粒度配置，前端基于权限码控制按钮可见性与路由可达性 |

### 3.3 知识维护与导入

| 需求编号 | 功能点 | 详细描述 |
| --- | --- | --- |
| F-KB-01 | 单文件导入 | 上传单个 PDF / Markdown / Word / TXT 文件 |
| F-KB-02 | 批量导入 | 多文件并发上传或拖拽目录导入，实时展示每个文件的解析状态（待解析→解析中→成功/失败） |
| F-KB-03 | 文档解析与切片 | 后端按格式解析文档内容，自动拆分为独立知识单元（Knowledge Unit），写入向量库 |
| F-KB-04 | 知识单元列表 | 分页查询：按标题、分类、状态筛选；展示编号、标题、分类、格式、数据权限摘要、创建人、更新时间、状态 |
| F-KB-05 | 知识单元详情 | 查看完整正文、标签、附件、已配置的数据权限实体清单 |
| F-KB-06 | 知识单元编辑 | 修改标题、正文、标签、附件；调整数据权限（弹窗勾选） |
| F-KB-07 | 批量删除 | 支持勾选多条知识单元一次性删除 |
| F-KB-08 | 数据权限配置弹窗 | 统一组件：勾选全局公开、多选部门、多选角色、多选人员，支持混合配置 |

### 3.4 AI 对话鉴权工作台

| 需求编号 | 功能点 | 详细描述 |
| --- | --- | --- |
| F-AI-01 | 登录态拦截 | 未登录或 Token 失效禁止进入对话页 |
| F-AI-02 | 提问输入 | 智能输入框，支持多轮对话 |
| F-AI-03 | 流式回复 | SSE 流式输出，Markdown 实时渲染 |
| F-AI-04 | 知识引用卡片 | 展示回答中引用的知识单元标题、来源、片段 |
| F-AI-05 | 权限缺失提示 | 召回但被鉴权过滤的知识单元以独立卡片明确告知"该单元您无访问权限" |
| F-AI-06 | 历史对话列表 | 按 session 管理，可切换查看与清空 |
| F-AI-07 | 问答缓存优先 | 命中已发布 FAQ 缓存时直接返回标准答案，跳过模型调用 |

### 3.5 数据看板

| 需求编号 | 功能点 | 详细描述 |
| --- | --- | --- |
| F-DASH-01 | 指标卡片 | Agent 访问次数、独立访问人数（UV）、知识单元总数、总 Token 消耗、平均响应时间 |
| F-DASH-02 | 常见问题 TOP 榜 | 按频次聚合的高频提问排行榜 |
| F-DASH-03 | 知识热度榜 | 最常访问的知识单元 TOP 榜 |
| F-DASH-04 | 趋势图 | 按日/周的访问趋势、Token 消耗走势、响应时间分布（折线图/柱状图） |

### 3.6 知识沉淀管理

| 需求编号 | 功能点 | 详细描述 |
| --- | --- | --- |
| F-SET-01 | FAQ 自动推荐 | 系统从历史对话挖掘的高频问题推荐列表，含推荐频次、关联知识单元、建议答案 |
| F-SET-02 | FAQ 审核发布 | 管理员可审核通过（可编辑标准化答案后发布）/驳回；发布后写入 FAQ 缓存 |
| F-SET-03 | 已发布 FAQ 库 | 管理已上线的 FAQ 问答对、缓存生效状态、命中统计 |
| F-SET-04 | 知识缺口列表 | 展示 AI 检索未命中或置信度过低的用户提问、频次、最近提问时间 |
| F-SET-05 | 一键建档 | 知识缺口项支持一键创建关联知识单元并跳转到编辑页 |

---

## 4. 核心业务流程

### 4.1 知识批量维护与权限配置流程

```
[知识管理员] 单/多文件上传
        │
        ▼
   [后端] 文档解析 → 文本切片 → 知识单元入库 → 向量化
        │
        ▼
[知识管理员] 选择目标知识单元 → 配置数据权限（全局/部门/角色/个人）
        │
        ▼
   [后端] 写入 unit_permissions → 即时生效
```

### 4.2 AI 鉴权问答流转流程

```
[用户] 登录 → AI 对话窗口输入问题
        │
        ▼
   [后端] 校验 JWT → 获取用户部门与角色
        │
        ▼
   [智能体] 向量检索 + 关键字召回候选知识单元 (召回集合 R)
        │
        ▼
   [智能体] 调用 POST /api/v1/knowledge/check-permissions (user_id, R)
        │
        ▼
   [鉴权引擎] 计算 authorized ∪ unauthorized
        │
        ▼
   [智能体] 用 authorized 组装 Prompt → 流式输出
        │
        ▼
   [响应] 同时展示 unauthorized 列表 → 权限缺失提示卡片
        │
        ▼
   [异步] 写入 qa_access_logs（用户、命中单元、Token、响应时长）
```

### 4.3 知识沉淀与 FAQ 闭环流程

```
[沉淀引擎] 定时任务：分析 qa_access_logs
        │
        ▼
   语义去重 + 频次聚合 → 达到阈值 → 自动生成 faqs（status=pending_review）
        │
        ▼
[知识管理员] FAQ 推荐列表 → 编辑标准答案 → 审核通过（approve）
        │
        ▼
   [后端] 更新 faqs.status=published → 写入 FAQ 缓存
        │
        ▼
[用户] 提问 → 命中 FAQ 缓存 → 直接输出标准答案
        │
        ▼
[沉淀引擎] 识别低相似度/无召回的提问 → 写入 knowledge_gaps
        │
        ▼
[知识管理员] 缺口列表 → 一键创建知识单元 → 补全知识库
```

---

## 5. 数据模型（核心表）

| 表名 | 关键字段 | 用途 |
| --- | --- | --- |
| `users` | id, username, password_hash, display_name, department_id, status | 用户主表 |
| `departments` | id, parent_id, name, leader_id, sort_order | 部门树 |
| `roles` | id, role_name, role_code, description | 角色定义 |
| `user_roles` | id, user_id, role_id | 用户-角色多对多 |
| `role_permissions` | id, role_id, permission_code, permission_type | 角色-操作权限 |
| `knowledge_units` | id, unit_code, title, content, summary, category, source_file_name, file_type, file_size, status, creator_id | 知识单元主表 |
| `unit_permissions` | id, unit_id, target_type(global/department/role/user), target_id | 四维数据权限 |
| `qa_access_logs` | id, session_id, user_id, question, answer, recalled_unit_ids_json, authorized_unit_ids_json, unauthorized_unit_ids_json, prompt_tokens, completion_tokens, total_tokens, response_time_ms | 问答访问日志 |
| `faqs` | id, question, answer, category, related_unit_id, source_type(manual/auto_mined), status(pending_review/published/rejected), hit_count, reviewer_id, reviewed_at | FAQ 推荐与发布 |
| `knowledge_gaps` | id, question_pattern, sample_questions_json, ask_count, last_asked_at, status(unresolved/resolved/ignored), resolved_unit_id | 知识缺口 |

详细字段定义见需求文档 §2.9.7。

---

## 6. 接口需求

> 路径规范见 ADR-0007：所有业务接口固定前缀 `/api/v1/`；资源名采用复数 + 连字符（如 `/knowledge-units`）；沉淀域路由已下沉到 `/faqs` 与 `/knowledge-gaps`（不再保留 `/settlement` 命名）；`PATCH` 用于部分更新、`PUT` 用于全量替换。

| 接口 | 方法 | 关键字段 | 说明 |
| --- | --- | --- | --- |
| `/api/v1/auth/login` | POST | username, password → access_token, user_info, permissions | 登录 |
| `/api/v1/org/departments` | GET | — | 部门树 |
| `/api/v1/org/users` | POST/PUT | 用户字段 | 新增/编辑 |
| `/api/v1/org/roles` | GET | — | 角色列表 |
| `/api/v1/org/roles/{id}/permissions` | POST | permission_codes[] | 权限分配 |
| `/api/v1/knowledge/import` | POST | files[] | 单/批量上传 |
| `/api/v1/knowledge-units` | GET | title, category, status, page | 分页查询 |
| `/api/v1/knowledge-units/{id}` | GET | — | 详情 |
| `/api/v1/knowledge-units/{id}` | PATCH | title, content, ... | 部分更新 |
| `/api/v1/knowledge-units/{id}/permissions` | POST | permissions[] | 权限配置 |
| `/api/v1/knowledge-units` | DELETE | ids[] | 批量删除 |
| `/api/v1/knowledge/check-permissions` | POST | user_id, unit_ids → authorized_unit_ids, unauthorized_unit_ids | 鉴权核心 |
| `/api/v1/ai/chat/stream` | POST | question, session_id → SSE | 流式问答 |
| `/api/v1/dashboard/metrics` | GET | — | 核心指标 |
| `/api/v1/dashboard/rankings/questions` | GET | — | FAQ TOP |
| `/api/v1/dashboard/rankings/units` | GET | — | 知识热度 TOP |
| `/api/v1/dashboard/stats/tokens` | GET | range | 趋势 |
| `/api/v1/faqs/recommendations` | GET | — | 推荐 FAQ |
| `/api/v1/faqs/{id}/review` | POST | action(approve/reject), edited_answer | 审核 |
| `/api/v1/knowledge-gaps` | GET | — | 知识缺口 |

### 6.x 补充接口（H19 修复同步补齐）

| 接口 | 方法 | 权限码 | 说明 |
| --- | --- | --- | --- |
| `/api/v1/auth/me` | GET | 需登录 | 当前用户信息 |
| `/api/v1/auth/logout` | POST | 需登录 | 登出（清 Redis 位图） |
| `/api/v1/ai/sessions` | POST | `ai:chat` | 创建会话（id 客户端生成 UUID） |
| `/api/v1/ai/sessions` | GET | `ai:chat` | 当前用户会话列表 |
| `/api/v1/ai/sessions/{id}` | GET | `ai:chat` | 会话详情 |
| `/api/v1/ai/sessions/{id}` | PATCH | `ai:chat` | 更新标题 |
| `/api/v1/ai/sessions/{id}` | DELETE | `ai:chat` | 删除会话 |
| `/api/v1/ai/chat/resume` | POST | `ai:chat` | 续接被 `interrupt` 挂起的会话 |
| `/api/v1/knowledge-gaps/{id}/create-unit` | POST | `knowledge:write` | 一键建档 |
| `/api/v1/org/users/{id}/reset-password` | POST | `user:write` | 重置密码 |
| `/api/v1/org/users/{id}/status` | PATCH | `user:write` | 启停用 |
| `/api/v1/faqs/{id}/review` | POST | `faq:review` | 审核（approve/reject + edited_answer） |
| `/api/v1/dashboard/stats/response-time` | GET | `dashboard:read` | 响应时间趋势 |
| `/api/v1/faqs/{id}` | PATCH | `faq:write` | 编辑 FAQ（仅 pending_review/published 可改） |

详细字段定义见需求文档 §2.9.8。

---

## 7. 前端模块划分

| 模块 | 职责 |
| --- | --- |
| 认证与权限控制 | Token 管理、登录态、动态菜单渲染、按钮级操作权限 |
| 组织架构管理 | 用户/角色/部门树形与列表 CRUD、角色权限分配 |
| 知识管理与批量导入 | 文件拖拽/并发上传、解析进度轮询、知识单元 CRUD |
| 数据权限配置组件 | 统一权限弹窗：全局/部门/角色/人员多选 |
| AI 对话工作台 | 多轮对话、流式 Markdown、引用卡片、权限缺失提示卡片 |
| 看板与图表 | 指标卡、TOP 榜、趋势图（ECharts） |
| 知识沉淀 | FAQ 推荐/审核、缺口列表、快速建档 |

---

## 8. 后端服务模块划分

| 服务 | 职责 |
| --- | --- |
| 认证鉴权 | JWT 签发校验、RBAC 拦截 |
| 组织架构服务 | 用户/角色/部门树 CRUD、映射关系 |
| 知识单元管理 | 上传、解析、切片、CRUD、向量化同步 |
| 数据权限引擎 | 计算允许/拒绝列表（核心鉴权接口实现方） |
| AI 鉴权检索 | 会话管理、向量+关键字混合召回、权限过滤、Prompt 组装、流式生成 |
| 数据看板统计 | 异步日志写入、聚合指标与排行榜 |
| 知识沉淀挖掘 | 定时/聚类挖掘高频问题、识别缺口 |
| FAQ 缓存 | 精确+语义匹配、缓存命中优先应答 |

---

## 9. 非功能需求

| 维度 | 要求 |
| --- | --- |
| 性能 | 单次问答端到端 P95 < 3s；FAQ 缓存命中 P95 < 200ms |
| 安全 | 密码 bcrypt 哈希；JWT 过期可控；接口 RBAC + 数据权限双层校验 |
| 可观测 | qa_access_logs 完整记录用户/单元/Token/耗时；看板可追溯 |
| 可扩展 | 数据权限维度可扩展（如未来加"密级"）；FAQ 挖掘算法可插拔 |
| 兼容性 | 文档格式：PDF / Markdown / Word(.docx) / TXT |
| 数据初始化 | 提供完整 SQL 建表脚本与种子数据（含示例账号、示例知识单元、示例 FAQ） |

---

## 10. 验收标准

- [ ] 能完成用户登录、角色/部门管理、菜单与按钮级操作权限分配
- [ ] 能通过界面完成单篇与批量文档导入，并成功拆分为知识单元完成检索入库
- [ ] 能对知识单元执行增删改查，支持混合配置全局/部门/角色/个人四类数据权限
- [ ] 用户满足部门/角色/个人/全局中**任意一种**权限即可访问知识单元
- [ ] AI 对话强制校验登录态并调用鉴权接口过滤未授权知识单元，对无权限召回项输出明确权限缺失提示
- [ ] 数据看板正确展示：访问次数、独立人数、知识单元数、常见问题榜、知识热度榜、Token 消耗、响应时间趋势
- [ ] 自动从历史对话挖掘高频问题生成推荐 FAQ，管理员可审核发布并写入缓存加速应答
- [ ] 自动识别未命中知识库的问题生成知识缺口列表，可查看提问频次

---

## 11. 风险与开放问题

| 风险/问题 | 应对/说明 |
| --- | --- |
| 大文档切片语义断裂 | 切片策略待细化（建议按段落/标题切分，相邻片段保留重叠窗口） |
| 向量库选型未定 | MySQL 环境受限可降级为全文索引 + 关键词；推荐独立向量库（如 pgvector/Chroma） |
| FAQ 语义去重阈值 | 频次阈值与相似度阈值需在演示数据上标定 |
| 鉴权性能 | 每次问答都要 check-permissions，需考虑缓存用户权限位图 |
| 缺口中"一键建档"的单元内容 | 默认从历史答案聚类生成，需人工编辑确认 |

---

## 12. 附录：需求追溯矩阵

| PRD 章节 | 需求文档章节 |
| --- | --- |
| §3.1 认证 | §2.9.3 登录与个人中心页 |
| §3.2 组织架构 | §2.9.3 组织架构与权限管理页 |
| §3.3 知识维护 | §2.9.3 知识维护与导入页；§2.9.5 前端模块；§2.9.6 知识单元管理服务 |
| §3.4 AI 对话 | §2.9.3 AI 对话鉴权工作台；§2.9.6 AI 鉴权检索服务 |
| §3.5 看板 | §2.9.3 数据看板页；§2.9.6 数据看板统计服务 |
| §3.6 知识沉淀 | §2.9.3 知识沉淀管理页；§2.9.6 知识沉淀挖掘服务 + FAQ 缓存服务 |
| §5 数据模型 | §2.9.7 数据表要求 |
| §6 接口 | §2.9.8 接口要求 |
| §4 业务流程 | §2.9.10 核心业务流程 |
| §10 验收标准 | §2.9.11 验收标准 |