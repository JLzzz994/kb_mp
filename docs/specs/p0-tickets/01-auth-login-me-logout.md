# 01 — 认证完整（登录 + 当前用户 + 登出，合并原 T01 + T02）

**What to build:** 端到端认证授权链路——三个端点（POST /login / GET /me / POST /logout）+ Django-style auth flow + JWT 签发+校验 + bcrypt 验证 + Redis 鉴权位图 + 全局 AppError handler + RBAC 拦截工厂。

**Blocked by:** 00 (P0 基础设施与数据库骨架)

**Status:** ready-for-agent

---

## Acceptance Criteria

- [ ] `POST /api/v1/auth/login` 接受 `{username, password}` 公开端点，正确凭据返回 `{access_token, token_type: "bearer", expires_in, user_info, permissions}` HTTP 200
- [ ] `POST /api/v1/auth/login` 错密码 / 不存在用户 → 401 `invalid_credentials`（不区分，防御枚举）
- [ ] `POST /api/v1/auth/login` `status=0` 用户 → 403 `user_disabled`
- [ ] `POST /api/v1/auth/login` 字段校验失败 → 422 `validation_failed`（username < 3 / password < 6）
- [ ] `GET /api/v1/auth/me` Bearer Token 有效 → 200 `{user_info, permissions}`（17 权限码）
- [ ] `GET /api/v1/auth/me` 无 Token → 401 `authentication_required`
- [ ] `GET /api/v1/auth/me` 过期 Token → 401 `invalid_access_token`
- [ ] `GET /api/v1/auth/me` 格式错误 Token → 401 `invalid_access_token`
- [ ] `POST /api/v1/auth/logout` Bearer Token 有效 → 204（清 Redis `auth:bitmap:{user_id}`）
- [ ] bcrypt cost=12 验证（hashes startswith `$2b$`）
- [ ] JWT HS256 / 8h TTL / Claims 包含 `sub=user_id / username / role_codes / iat / exp`
- [ ] Redis 写入 `auth:bitmap:{user_id}` 5 分钟 TTL（JSON 列表）
- [ ] `get_current_user` 优先读 Redis 位图，缺失则重算
- [ ] `require_permission(*codes)` 工厂返回 `Depends` 实例，403 `permission_denied`
- [ ] `AppError` 全局 handler 统一返回 `{detail, error_code, request_id}`
- [ ] `tests/test_auth_login.py` 5 用例全绿
- [ ] `tests/test_auth_me.py` 4 用例全绿
- [ ] `tests/test_auth_token.py` 2 用例全绿
- [ ] `tests/test_auth_permission.py` 4 用例全绿（含位图失效重算）

---

## 进一步说明

参考文档：
- `docs/specs/M1-认证鉴权.md`（路由器 + 接口契约 + 17 权限码）
- `docs/impl/IMPL-M1-认证鉴权.md`（§2.3 AuthService / §2.4 JWTIssuer / §2.4 PasswordHasher / §2.4 RedisClient 完整方法级实现）
- `docs/接口约定文档.md` §2.5 / §7.1（JWT Bearer + LoginRequest/Response schema + 错误码）
- `docs/数据对象文档.md` §2.1-§2.5（users / roles / user_roles / role_permissions）

实现顺序（自下而上）：
1. exceptions 7 个（如未在 PR0 完成）
2. `AuthRepository` 5 方法（find_by_username / list_role_codes / list_role_ids / list_dept_ids_with_ancestors / list_permissions / load_current_user）
3. `AuthService.login` / `load_current_user` / `me` / `logout`
4. `AuthRouter` 3 端点
5. `tests/test_auth_*.py` 4 文件 15 用例

TDD 顺序：先 `test_login_success` 跑红 → 写 Repository → Service → Router → 跑绿；再 `test_login_wrong_password` 跑红 → 补 `InvalidCredentialsError` → 跑绿；以此类推。