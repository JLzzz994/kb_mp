# 04 — 用户管理 + 端到端演示链路（CRUD + Redis 位图失效 + 端到端 P0 验证）

**What to build:** 用户CRUD + 启停用 + 重置密码 + 7 端点 + 端到端 P0 演示链（admin 登录 → 部门树 → 创建用户 → 分配角色 → 验证权限）+ seed.py 幂等种子脚本。

**Blocked by:** 01 (认证完整) + 02 (部门管理) + 03 (角色管理 + 权限分发)

**Status:** ready-for-agent

---

## Acceptance Criteria

- [ ] `GET /api/v1/org/users?page=1&page_size=20` RBAC `user:read` → 200 含 `role_codes / department_name`
- [ ] `GET /api/v1/org/users` 支持 `?department_id=&status=&keyword=` 筛选
- [ ] `GET /api/v1/org/users/{id}` RBAC `user:read` → 200 完整 user record
- [ ] `POST /api/v1/org/users` RBAC `user:write` → 201 创建用户
- [ ] `POST /api/v1/org/users` username 重复 → 409 `username_conflict`
- [ ] `POST /api/v1/org/users` 密码 bcrypt 哈希（`hashes startswith $2b$`）
- [ ] `POST /api/v1/org/users` 事务保证 users + user_roles 原子写入
- [ ] `PUT /api/v1/org/users/{id}` RBAC `user:write` → 200 全量替换（含 role_ids）
- [ ] `PATCH /api/v1/org/users/{id}/status` RBAC `user:write` → 204（停用时清 Redis 位图）
- [ ] `POST /api/v1/org/users/{id}/reset-password` RBAC `user:write` → 204（清 Redis 位图）
- [ ] `scripts/seed.py` 幂等插入 3 用户（admin / kadmin / alice）+ 3 角色 + 13 权限码（system_admin 17 码，kadmin 知识管理子集，alice 仅 user:read + ai:chat + gap:read + faq:read）
- [ ] `tests/test_org_users.py` 5 用例全绿
- [ ] `tests/test_e2e_p0_demo.py` 端到端链：admin 登录 → 部门树 → 创建用户 → 分配 knowledge_admin → 验证权限流转
- [ ] `uv run ruff format --check . && uv run ruff check . && uv run pytest` 三件套全绿
- [ ] `alembic upgrade head` + `python scripts/seed.py` + `uv run uvicorn app.main:app` 冷启动 30s 内完成

---

## 进一步说明

参考文档：
- `docs/specs/M2-组织架构管理.md`（§5 用户路由 + UserService 6 方法）
- `docs/impl/IMPL-M2-组织架构管理.md`（§3 UserService + UserRepository 8 方法）
- `docs/接口约定文档.md` §7.2（用户 + 角色 + 部门端点契约）
- `docs/数据对象文档.md` §2.4 user_roles + §2.5 role_permissions

实现顺序：
1. `UserRepository` 8 方法（含 `_batch_role_codes` 优化）
2. `UserService` 6 方法（list / get / create / update / set_status / reset_password）
3. `schemas/user_schema.py`（UserCreate / UserUpdate / UserResponse / UserListResponse / ResetPasswordRequest / UserStatusPatch）
4. `OrgRouter` 7 端点
5. `scripts/seed.py`
6. `tests/test_org_users.py` 5 用例
7. `tests/test_e2e_p0_demo.py` 端到端

TDD 顺序：先 `test_list_users_paginated` → UserRepository → UserService → Router → 跑绿；再 `test_create_duplicate_username` → Service 加 `UsernameConflictError` → 跑绿；最后 `test_e2e_p0_demo` 验证完整链路。

P0 完成后即可进入 P1（M3 知识资产管理）。