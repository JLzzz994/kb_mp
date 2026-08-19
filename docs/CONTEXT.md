# kb_mp —— Context（领域词汇表）

# P0 编码阶段词汇（仅业务概念，无实现细节）

## 角色 (Role)

| 术语 | 精确含义 | 不包含 |
| --- | --- | --- |
| **System Administrator** | 拥有全部 17 权限码的内置角色；可 CRUD 用户/角色/部门，可查看系统看板 | 业务流程编排 |
| **Knowledge Administrator** | 拥有 14 权限码（知识管理 + AI + 看板 + FAQ 全部），可 CRUD 知识单元、审核 FAQ、管理缺口 | 用户/角色/部门写权限 |
| **Regular User** | 拥有 4 权限码（ai:chat + knowledge:read + faq:read + gap:read）；仅 AI 对话 + 知识查询 | 后台管理 |

## 用户 (User)

| 术语 | 精确含义 |
| --- | --- |
| **User** | 系统登录主体（独立于员工/客户）；通过 `username` + `password` 认证 |
| **UserEntity** | 纯领域实体，无密码字段，无 ORM 依赖 |
| **UserWithPassword** | 仅 Repository 内部使用字段扩展（含 `password_hash` 字段） |
| **CurrentUser** | 登录后注入请求上下文的最小主体（含 `dept_ids + role_ids + permission_view`） |
| **User Status** | 单一状态字段 `status`（1=启用 / 0=停用）；不存独立的"已删除"状态 |

## 部门 (Department)

| 术语 | 精确含义 |
| --- | --- |
| **Department** | 树形组织节点（`parent_id` 自引用）；用户单一归属部门 |
| **Department Tree** | 嵌套 `children[]` 结构；用 `sort_order` + `id` 稳定排序 |
| **Ancestor Departments** | 用户的当前部门 + 所有父级部门（用于部门权限向上继承） |

## 权限 (Permission)

| 术语 | 精确含义 |
| --- | --- |
| **Permission Code** | 形如 `domain:action` 的细粒度操作码（17 个）；不与角色耦合 |
| **17 Permission Codes** | 完整清单: user:read/write, role:read/write, dept:read/write, knowledge:read/write/delete/assign_permission/check, ai:chat, dashboard:read, faq:read/write/review, gap:read |
| **Operation Permission** | 角色可操作的权限集合（细粒度，存 `role_permissions` 表） |
| **Data Permission** | 知识单元四维访问控制（global / department / role / user）；OR 逻辑合并 |
| **Auth Bitmap** | 用户 `user_id` → 17 码子集的 Redis 缓存（key: `auth:bitmap:{user_id}`，TTL 5 分钟） |

## 知识 (Knowledge)

| 术语 | 精确含义 |
| --- | --- |
| **Knowledge Unit** | 文档解析切片后的最小存储单元（`unit_code` 唯一） |
| **Content Hash** | 知识单元原文 SHA-256 摘要（导入幂等校验） |
| **Question Hash** | FAQ 问题文本 SHA-1 摘要（Redis 缓存 key + DB UNIQUE） |
| **FAQ Standard Answer** | 知识管理员审核发布的标准化答案（持久化 + 缓存） |
| **FAQ Cache** | Redis hash（key: `faq:cache:{question_hash}`，含 `unit_updated_at` 版本控制） |

## AI 对话 (Chat)

| 术语 | 精确含义 |
| --- | --- |
| **Chat Session** | 多轮对话会话（id 由客户端生成 UUID；含 `history_json` + `slots` + `pending_turn`） |
| **Pending Turn** | 鉴权/召回为空时挂起的一轮问答草稿；resume 接口补全 |
| **Slot** | 对话中已确认的实体或上下文（interrupt 续接用） |

## 看板 (Dashboard)

| 术语 | 精确含义 |
| --- | --- |
| **Indicator** | 单一指标（如 access_count / uv / total_tokens） |
| **Ranking** | TOP 列表（faq / unit 热度） |
| **Trend** | 时间序列分桶数据（按日 / 按周） |

# 锁定决策（P0 阶段）

| # | 决策 | 锁定值 | 决议 |
| --- | --- | --- | --- |
| Q1 | JWT secret 来源 | `.env` 硬编码 + 启动脚本生成 | 演示期 |
| Q2 | bcrypt 测试 cost | 测试 `cost=4`，生产 `cost=12` | 单测 < 2s |
| Q3 | Alembic 迁移策略 | 1 个 `0001_initial.py` 手动写 | 演示期 |
| Q4 | Redis 启动策略 | 启动 ping，挂了 raise fast-fail | 关键决策 → ADR-0003 |
| Q5 | seed.py 幂等 | `--reset` 强制重置，默认插入缺失项 | 关键决策 → ADR-0003 |
| Q6 | seed 权限码分配 | system_admin 17 / knowledge_admin 14 / regular_user 4 | 演示三家权限层 |
| Q7 | seed 部门结构 | 3 部门 2 层嵌套（研发中心 / 研发一组 / 研发二组） | 演示部门树 + 祖先继承 |
| Q8 | ORM 字段命名 | Python 名 = DDL 列名 = Schema 字段名（snake_case） | 调试可读性 |

# 错误码命名规范

| 层级 | 命名模式 | 示例 |
| --- | --- | --- |
| 资源 | `{resource}_not_found` | `user_not_found` / `department_not_found` |
| 权限 | `permission_denied` | （统一主码，data 含缺失权限码列表） |
| 鉴权 | `authentication_required` / `invalid_access_token` | |
| 业务约束 | `{resource}_{constraint}` | `department_not_empty` / `permission_conflict` |
| 输入 | `validation_failed` | （422 通用，Pydantic 错误附 field） |

# 上下游模块

| 上游 | 下游 | 关系 |
| --- | --- | --- |
| Auth Repository | Auth Service | 数据访问 |
| Auth Service | Knowledge Service | 加载 `CurrentUser` |
| Org Service | Auth Service | 权限变更 → `del_bitmap` |
| Org Service | Knowledge Service | 部门 CRUD → 知识权限校验 |
| Knowledge Service | AI Service | 检索 → 鉴权 → 生成 |
| AI Service | FAQ Service | 缓存命中 → Redis 同步 |
| Knowledge Service | FAQ Service | 缺口触发 → 一键建档 |

# 术语挑战（已决策）

- **「账户」**：本项目无"账户"概念（Notion 中所有"账户"= User，已废弃该词）
- **「会话」**：Session = 用户的 AI 对话会话（id 由客户端生成 UUID），不与"登录会话"（Token Session）混淆
- **「权限」**：Permission Code（资源:动作）= 位图缓存中的 "1"或"0"；不要混淆"权限"和"角色权限关联表"（role_permissions）