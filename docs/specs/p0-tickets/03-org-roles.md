# 03 — 角色管理 + 权限分发（17 权限码 + 批量位图失效）

**What to build:** 角色列表 + 权限查询 + 角色权限分配 + 17 码白名单校验 + 批量 Redis 位图失效。包含 Phase 4 修复的 `del_bitmaps_by_role` 串接 + RedisClient 抽象方法。

**Blocked by:** 00 (P0 基础设施与数据库骨架)

**Status:** ready-for-agent

---

## Acceptance Criteria

- [ ] `GET /api/v1/org/roles` RBAC `role:read` → 200 返回 3 角色列表（含 `permissions: list[str]`）
- [ ] `GET /api/v1/org/permissions` RBAC `role:read` → 200 返回 17 权限码白名单
- [ ] `POST /api/v1/org/roles/{id}/permissions` RBAC `role:write` → 204
- [ ] `POST /api/v1/org/roles/{id}/permissions` 17 码全部合法 → 204
- [ ] `POST /api/v1/org/roles/{id}/permissions` 含非 17 码 → 422 `invalid_permission_code`
- [ ] `POST /api/v1/org/roles/{id}/permissions` 不存在角色 → 404 `role_not_found`
- [ ] `POST /api/v1/org/roles/{id}/permissions` 权限变更后所有持有该角色的用户 Redis `auth:bitmap:{user_id}` 被 DEL（`del_bitmaps_by_role` 串接）
- [ ] `GET /api/v1/org/roles` 含 `system_admin` 角色的 17 权限码验证（测试期望 `len == 17`）
- [ ] `tests/test_org_roles.py` 3 用例全绿：list_includes_sys_admin / assign_validates_17_codes / assign_clears_user_bitmaps

---

## 进一步说明

参考文档：
- `docs/specs/M2-组织架构管理.md`（§5 角色路由 + RoleService.assign_permissions）
- `docs/impl/IMPL-M2-组织架构管理.md`（§4 RoleService.assign_permissions + 17 码白名单校验）
- `docs/impl/IMPL-M1-认证鉴权.md` §2.4（RedisClient `del_bitmaps_by_role` 实现）
- `docs/specs/M1-认证鉴权.md` §4.1（PermissionCode 17 码 + ALL_PERMISSION_CODES）
- `docs/数据对象文档.md` §2.5（完整 17 码清单）

实现顺序：
1. `RoleRepository` 4 方法（list_all_with_permissions / list_users_with_role / replace_role_permissions / batch_find_by_ids）
2. `RoleService.list` + `list_all_permission_codes` + `assign_permissions`（含 17 码白名单 + `del_bitmaps_by_role` 串接）
3. `schemas/role_schema.py`（RoleResponse / AssignPermissionsRequest）
4. `OrgRouter` 3 端点
5. `tests/test_org_roles.py` 3 用例

TDD 顺序：`test_list_includes_sys_admin` → list → 跑绿 → `test_assign_validates_17_codes` → Service 白名单校验 → 跑绿 → `test_assign_clears_user_bitmaps` → 串接 `del_bitmaps_by_role` → 跑绿。