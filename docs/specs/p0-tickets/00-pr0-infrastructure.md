# 00 — P0 基础设施与数据库骨架（Prefactoring）

**What to build:** 从空骨架搭建 P0 编码所需的基础设施层——数据库连接 / 配置 / 异常体系 / 领域实体 / Redis / JWT / 密码哈希 / lifespan / Alembic 迁移 / DI 装配 / 测试 conftest。这是后续 4 个垂直切片的共同前置，本工单完成后 T01-T04 即可并行开工。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

**类型：** wide refactor（基础设施层一次性铺设，CI 全程绿，blast radius 受控）

---

## Acceptance Criteria

- [ ] `app/database.py` 含 SQLAlchemy 2.0 async engine + `AsyncSessionLocal` + `get_db()` Depends + 11 张表 ORM 类（UserRecord / DepartmentRecord / RoleRecord / UserRoleRecord / RolePermissionRecord / KnowledgeUnitRecord / UnitPermissionRecord / QaAccessLogRecord / ChatSessionRecord / FaqRecord / KnowledgeGapRecord）
- [ ] `app/config/settings.py` 扩展字段：`jwt_secret / bcrypt_cost / redis_url / auth_bitmap_ttl_seconds / jwt_algorithm / jwt_expire_minutes`
- [ ] `app/common/errors.py` 增补 7 个异常类：`InvalidCredentialsError / UserDisabledError / UserNotFoundError / DepartmentNotFoundError / DepartmentNotEmptyError / UsernameConflictError / RoleNotFoundError`
- [ ] `app/domain/{user,department,permission}.py` 3 个 dataclass：`UserEntity / UserWithPassword / CurrentUser / DepartmentEntity / PermissionCode（17 码 + ALL_PERMISSION_CODES）`
- [ ] `app/infrastructure/redis_client.py` 含 `RedisClient` 类（通用 KV + 鉴权位图 + Hash + 单例 `get_redis()`）
- [ ] `app/infrastructure/jwt.py` 含 `JWTIssuer` 类（HS256，8h TTL）
- [ ] `app/infrastructure/password_hasher.py` 含 `PasswordHasher` 类（bcrypt cost=12）
- [ ] `app/infrastructure/lifespan.py` 扩展：启动 Redis + 关闭、`pytest --no-cov` 豁免
- [ ] `alembic/` 初始化：env.py + script.py.mako + `versions/0001_initial.py`（11 张表创建，含 uk + idx + chk_target_consistency CHECK 约束）
- [ ] `app/api/dependencies.py` 占位：`get_current_user` + `require_permission` 工厂 + 各 Service Depends 占位（具体实现留给 T01+）
- [ ] `tests/conftest.py` 基础：async_engine + async_client + `seeded_admin` / `admin_token` / `regular_user_token` / `redis_client` fixture
- [ ] `uv run pytest -k health` 仍通过（healthcheck 端点不破坏）
- [ ] `alembic upgrade head` 能成功创建 11 张表
- [ ] `uv run ruff format --check . && uv run ruff check . && uv run pytest` 三件套全绿

---

## Out of Scope

- 任何 Service / Repository / Router 业务实现（留给 T01-T05）
- bcrypt 算法切换（成本固定 12）
- JWT 密钥自动生成（演示期用 `.env` 硬编码）
- Redis 集群 / 哨兵模式
- Alembic 升级链（仅 1 个 0001_initial.py）
- Metrics / Tracing / Logging 接入

---

## 进一步说明

按以下顺序施工（dependency order）：
1. `database.py`（11 张表 ORM）—— 大块，但全 local 引用
2. `settings.py` 扩展字段
3. `errors.py` 7 个异常
4. `domain/*.py` 3 个 dataclass
5. `infrastructure/{redis_client,jwt,password_hasher}.py` 3 个 infra
6. `infrastructure/lifespan.py` 扩展
7. `alembic/` 三件套 + 0001_initial.py
8. `dependencies.py` 占位
9. `tests/conftest.py`
10. 跑 ruff + pytest 三件套

参考文档：
- `docs/specs/M1-认证鉴权.md`（PermissionCode 17 码 + ALL_PERMISSION_CODES）
- `docs/specs/M2-组织架构管理.md`（UserResponse / UserListResponse Schema）
- `docs/数据对象文档.md`（11 张表字段定义）
- `docs/impl/IMPL-M1-认证鉴权.md`（§2.1 版本 PermissionCode 完整清单）
- `docs/impl/IMPL-M2-组织架构管理.md`（§3 关键 Pydantic Schema）
- `docs/adr/0001-deployment-mysql-milvus-redis.md`（部署架构决策）
- `docs/adr/0002-langgraph-8-nodes.md`（LangGraph 决策，Phase 2 引用）
- `docs/adr/0007-path-style-and-version.md`（路径风格冻结）

待 T01-T04 完成后，PR0 为它们提供稳定依赖接口。