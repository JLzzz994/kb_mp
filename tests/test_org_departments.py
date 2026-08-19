"""部门管理端点测试（5 用例）。

> tree / create / invalid_parent / delete_with_children / delete_with_members

> T02 实现要求（简报锁定决策）：
> - GET 树 → dept:read；POST/PUT/DELETE → dept:write
> - 树按 sort_order ASC, id ASC 递归；节点含 member_count
> - 删除保护：子部门或成员 → 422 department_not_empty
> - parent_id 不存在 → 404 department_not_found
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def root_dept_id(async_client: AsyncClient, admin_token) -> int:
    """查询根部门 id（种子仅有 1 个根）。"""
    headers = _auth(admin_token)
    resp = await async_client.get("/api/v1/org/departments", headers=headers)
    assert resp.status_code == 200
    tree = resp.json()
    assert len(tree) == 1
    return tree[0]["id"]


@pytest.mark.asyncio
async def test_list_tree(async_client: AsyncClient, admin_token, root_dept_id):
    """tree：树形组装正确，子节点嵌在 parent 下；节点含 member_count。"""
    headers = _auth(admin_token)

    # 新增 2 个子部门验证排序 + 嵌套
    resp_a = await async_client.post(
        "/api/v1/org/departments",
        headers=headers,
        json={"name": "子部门A", "parent_id": root_dept_id, "sort_order": 1},
    )
    assert resp_a.status_code == 201, resp_a.text
    resp_b = await async_client.post(
        "/api/v1/org/departments",
        headers=headers,
        json={"name": "子部门B", "parent_id": root_dept_id, "sort_order": 2},
    )
    assert resp_b.status_code == 201, resp_b.text

    resp = await async_client.get("/api/v1/org/departments", headers=headers)
    assert resp.status_code == 200, resp.text
    tree = resp.json()
    assert isinstance(tree, list) and len(tree) == 1

    root = tree[0]
    assert root["id"] == root_dept_id
    assert root["name"] == "研发中心"
    assert root["member_count"] == 1  # admin 本身
    assert root["parent_id"] is None
    # 子部门按 sort_order 升序
    assert [c["sort_order"] for c in root["children"]] == [1, 2]
    assert [c["name"] for c in root["children"]] == ["子部门A", "子部门B"]
    assert all(c["parent_id"] == root["id"] for c in root["children"])
    assert root["children"][0]["member_count"] == 0
    assert root["children"][1]["member_count"] == 0


@pytest.mark.asyncio
async def test_create_department(async_client: AsyncClient, admin_token, root_dept_id):
    """create：POST 创建部门，返回完整节点。"""
    headers = _auth(admin_token)
    resp = await async_client.post(
        "/api/v1/org/departments",
        headers=headers,
        json={"name": "新部门", "parent_id": root_dept_id, "sort_order": 0},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "新部门"
    assert body["parent_id"] == root_dept_id
    assert body["sort_order"] == 0
    assert body["member_count"] == 0
    assert body["children"] == []
    assert isinstance(body["id"], int) and body["id"] > 0


@pytest.mark.asyncio
async def test_create_with_invalid_parent(async_client: AsyncClient, admin_token, root_dept_id):
    """invalid_parent：parent_id 指向不存在的部门 → 404 department_not_found。"""
    headers = _auth(admin_token)
    resp = await async_client.post(
        "/api/v1/org/departments",
        headers=headers,
        json={"name": "孤儿部门", "parent_id": 99999, "sort_order": 0},
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "department_not_found"


@pytest.mark.asyncio
async def test_delete_dept_with_children(async_client: AsyncClient, admin_token, root_dept_id):
    """delete_with_children：根部门有子部门时尝试删除 → 422 department_not_empty。"""
    headers = _auth(admin_token)
    # 创建子部门
    child_resp = await async_client.post(
        "/api/v1/org/departments",
        headers=headers,
        json={"name": "子部门", "parent_id": root_dept_id, "sort_order": 0},
    )
    assert child_resp.status_code == 201

    # 尝试删除根部门（有子部门）→ 422
    resp = await async_client.delete(f"/api/v1/org/departments/{root_dept_id}", headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "department_not_empty"


@pytest.mark.asyncio
async def test_delete_dept_with_members(async_client: AsyncClient, admin_token, root_dept_id):
    """delete_with_members：admin 所在的根部门有 1 个成员 → 删除应被保护。"""
    headers = _auth(admin_token)
    resp = await async_client.delete(f"/api/v1/org/departments/{root_dept_id}", headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "department_not_empty"
