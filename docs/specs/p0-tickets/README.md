# P0 编码工单 — Tracer-Bullet 拆分

kb_mp P0 阶段（M1 认证 + M2 组织架构）编码分 5 个工单，按依赖顺序实施。

## 工单依赖图

```
[00 PR0]
  └─→ [01 认证完整]
  └─→ [02 部门管理]      ─→┐
  └─→ [03 角色+权限分发]  ─→├─→ [04 用户管理 + 端到端]
                            │
       [01]──────────────────┘
```

## 工单清单

| # | Title | Blocked by | 类型 |
| --- | --- | --- | --- |
| 00 | [P0 基础设施与数据库骨架](./00-pr0-infrastructure.md) | None | wide refactor（prefactoring） |
| 01 | [认证完整（登录 + 当前用户 + 登出）](./01-auth-login-me-logout.md) | 00 | tracer-bullet |
| 02 | [部门管理（部门树 + CRUD + 删除保护）](./02-org-departments.md) | 00 | tracer-bullet |
| 03 | [角色管理 + 权限分发（17 码 + 批量位图失效）](./03-org-roles.md) | 00 | tracer-bullet |
| 04 | [用户管理 + 端到端演示链路](./04-org-users-e2e.md) | 01 + 02 + 03 | tracer-bullet |

## 执行顺序

1. **00 PR0** 必须先做（基础设施）
2. **00 PR0** 完成后，**01 / 02 / 03** 4 条可并行开工（无相互依赖）
3. **04** 必须等 01 + 02 + 03 全部完成（UserService 依赖 AuthService + RoleService + DepartmentService）

## 端到端 P0 演示链（04 完成时验证）

```
1. POST /api/v1/auth/login {admin: Admin@123} → 200 + token + 17 权限码
2. GET /api/v1/org/departments → 200 部门树
3. POST /api/v1/org/users {newbie: Newbie@123, knowledge_admin} → 201
4. POST /api/v1/auth/login {newbie: Newbie@123} → 200 + 知识管理子集权限
5. PATCH /api/v1/org/users/{newbie}/status {0} → 204（admin 操作）
6. POST /api/v1/auth/login {newbie} → 403 user_disabled
```

## 验收门禁

P0 完成后必须通过：

```bash
# 1. 格式
uv run ruff format --check .

# 2. Lint
uv run ruff check .

# 3. 测试
uv run pytest -v

# 4. 端到端
# 演示期：手动 curl 或 httpx 脚本跑上面的 6 步
```

## 总文件清单（PR0 + 01 + 02 + 03 + 04 全部完成后）

新增：
- `app/database.py` / `app/infrastructure/{redis_client, jwt, password_hasher, lifespan}.py`
- `app/domain/{user, department, permission}.py`
- `app/services/{auth_service, department_service, user_service, role_service}.py`
- `app/repositories/{auth_repository, department_repository, user_repository, role_repository}.py`
- `app/api/{app, dependencies}.py` 扩展
- `app/api/routers/{auth_router, org_router}.py`
- `app/api/schemas/{auth_request, auth_response, department_schema, user_schema, role_schema}.py`
- `alembic/{env.py, script.py.mako, versions/0001_initial.py}`
- `scripts/seed.py`
- `tests/conftest.py` + `tests/test_auth_*.py` × 4 + `tests/test_org_*.py` × 3 + `tests/test_e2e_p0_demo.py`

修改：
- `app/api/app.py`（注册路由 + 全局 handler）
- `app/config/settings.py`（扩展字段）
- `app/common/errors.py`（增补 7 个异常）
- `app/main.py`（lifespan 注入）
- `pyproject.toml`（如缺 pytest-asyncio / httpx 等，回 Phase 2A 已补）

## 下一步

- 00 PR0 完成后方可启动 01 / 02 / 03（并行）
- 04 阻塞依赖：01 + 02 + 03 全过
- 全部完成后进入 P1（M3 知识资产管理）