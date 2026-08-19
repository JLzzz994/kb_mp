# 02 — 部门管理（部门树 + CRUD + 删除保护）

**What to build:** 部门树查询 + 部门 CRUD + 删除保护 + RBAC 拦截 `dept:*`。可在 PR0 完成后立即开始（与 T01 / T03 / T04 并行）。

**Blocked by:** 00 (P0 基础设施与数据库骨架)

**Status:** ready-for-agent

---

## Acceptance Criteria

- [ ] `GET /api/v1/org/departments` RBAC `dept:read` → 200 返回完整树形（嵌套 `children[]`）
- [ ] 每个树节点含 `id / name / parent_id / leader_id / member_count / children`
- [ ] 树按 `sort_order ASC, id ASC` 排序（递归）
- [ ] `POST /api/v1/org/departments` RBAC `dept:write` → 201 创建部门
- [ ] `POST /api/v1/org/departments` `parent_id` 不存在 → 404 `department_not_found`
- [ ] `PUT /api/v1/org/departments/{id}` RBAC `dept:write` → 200 更新
- [ ] `DELETE /api/v1/org/departments/{id}` RBAC `dept:write` → 204 删除
- [ ] `DELETE /api/v1/org/departments/{id}` 有子部门 → 422 `department_not_empty`
- [ ] `DELETE /api/v1/org/departments/{id}` 有成员 → 422 `department_not_empty`
- [ ] `DELETE /api/v1/org/departments/{id}` 不存在 → 404 `department_not_found`
- [ ] `tests/test_org_departments.py` 5 用例全绿：tree / create / invalid_parent / delete_with_children / delete_with_members

---

## 进一步说明

参考文档：
- `docs/specs/M2-组织架构管理.md`（§5 路由 + §5 业务方法 + §10 测试）
- `docs/impl/IMPL-M2-组织架构管理.md`（§2 DepartmentRepository 7 方法 + §2 DepartmentService 4 方法 / 完整实现）
- `docs/数据对象文档.md` §2.2 departments 表字段

实现顺序：
1. `DepartmentRepository` 7 方法
2. `DepartmentService.list_tree`（内存组装树关键）+ `create`（parent_id 校验）+ `update` + `delete`（删除保护）
3. `schemas/department_schema.py`（DepartmentNode / DepartmentCreate / DepartmentUpdate）
4. `OrgRouter` 4 端点
5. `tests/test_org_departments.py` 5 用例

TDD 顺序：`test_list_tree` → 树形组装 → Repository → Service → Router；`test_create_invalid_parent` → Service 加校验 → 跑绿。