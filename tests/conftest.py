"""测试 conftest：SQLite 内存 + seeded fixtures + Redis fake + bcrypt cost=4。

> PR0 + T01：基础设施级 fixtures（DB engine / app client / seed users）。
> 后续模块（M2~M6）按需扩展。
> 测试用 SQLite 内存（不依赖 MySQL），`MEDIUMTEXT` patch 为 `Text` 兼容。
"""

from __future__ import annotations

import os

# 必须在导入 app 之前设置（触发 lifespan 中的 pytest 豁免分支）
os.environ.setdefault("PYTEST_CURRENT_TEST", "conftest")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Text
from sqlalchemy.dialects import mysql as _mysql_dialect
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# ── SQLite 兼容补丁：MEDIUMTEXT → Text ─────────────────────────────
# SQLAlchemy 在 SQLite 上不支持 MEDIUMTEXT；测试时替换为 TEXT。
# 必须在 database.py 导入之前执行。
_mysql_dialect.MEDIUMTEXT = Text

# ── 临时把 settings.database_url 切到 sqlite 内存（导入前生效） ──
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.api.app import app  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.domain.permission import ALL_PERMISSION_CODES, PermissionCode  # noqa: E402
from app.infrastructure.database import (  # noqa: E402
    BaseORM,
    DepartmentRecord,
    RolePermissionRecord,
    RoleRecord,
    UserRecord,
    UserRoleRecord,
    get_session_factory,
)
from app.infrastructure.jwt import JWTIssuer  # noqa: E402
from app.infrastructure.password_hasher import PasswordHasher  # noqa: E402
from app.infrastructure.redis_client import get_redis  # noqa: E402


# ── 引擎与 Session（SQLite 内存） ─────────────────────────────


def _make_async_engine():
    """构造 SQLite 内存引擎（StaticPool，演示 / 真实服务 e2e 复用）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


@pytest_asyncio.fixture
async def async_engine():
    """每个测试一个 SQLite 内存引擎 + create_all / drop_all。

    使用 StaticPool 保证所有 session 共享同一连接，否则 per-request session
    会拿到独立的 in-memory DB 导致 POST 创建的数据在 GET 时看不到。
    """
    engine = _make_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncSession:
    factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# ── 应用覆盖（注入测试引擎 + fake redis） ─────────────────────────────


@pytest_asyncio.fixture
async def app_with_overrides(async_engine, fake_redis):
    """构造带 DB/Redis 覆盖的 FastAPI app 实例。"""
    from app.infrastructure.database import get_db

    # 每次请求新 session（与 async_engine 共享连接 + StaticPool）
    factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)

    async def _get_db_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_redis] = lambda: fake_redis
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(app_with_overrides) -> AsyncClient:
    transport = ASGITransport(app=app_with_overrides)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ── Redis fake（避免依赖真实 Redis） ─────────────────────────────


class FakeRedis:
    """最小 fake redis：内存存储 + bitmap 仿真。"""

    def __init__(self) -> None:
        self._kv: dict[str, str] = {}
        self._hash: dict[str, dict[str, str]] = {}

    async def set_bitmap(self, *, user_id, permissions, ttl):
        import json

        self._kv[f"auth:bitmap:{user_id}"] = json.dumps(permissions)

    async def get_bitmap(self, user_id):
        import json

        raw = self._kv.get(f"auth:bitmap:{user_id}")
        return json.loads(raw) if raw else None

    async def del_bitmap(self, user_id):
        self._kv.pop(f"auth:bitmap:{user_id}", None)

    async def del_bitmaps_by_role(self, role_id, user_ids):
        return 0

    async def set(self, key, value, ex=None):
        self._kv[key] = value if isinstance(value, str) else str(value)

    async def get(self, key):
        return self._kv.get(key)

    async def delete(self, key):
        # 同时清 kv 和 hash（演示版 fake；真实 Redis 是 KEYS 统一处理）
        in_kv = self._kv.pop(key, None) is not None
        in_hash = self._hash.pop(key, None) is not None
        return int(in_kv or in_hash)

    async def exists(self, key):
        return int(key in self._kv)

    async def ping(self):
        return True

    async def aclose(self):
        return None

    async def hset(self, key, mapping):
        self._hash.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})
        return 1

    async def hgetall(self, key):
        return dict(self._hash.get(key, {}))

    async def hdel(self, key, *fields):
        h = self._hash.get(key, {})
        count = sum(int(h.pop(f, None) is not None) for f in fields)
        return count


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr("app.api.dependencies.get_redis", lambda: fake)
    monkeypatch.setattr("app.infrastructure.lifespan.get_redis", lambda: fake)
    monkeypatch.setattr("app.services.auth_service.get_redis", lambda: fake)
    return fake


# ── 种子 fixtures ─────────────────────────────


@pytest.fixture
def fast_hasher() -> PasswordHasher:
    """测试用 bcrypt hasher，cost=4 加速（CONTEXT.md 锁定决策 Q2）。"""
    return PasswordHasher(cost=4)


@pytest_asyncio.fixture
async def seeded_admin(db_session, fast_hasher):
    """插入 admin + system_admin + 17 权限码 + 1 个部门。返回 user_id。"""
    # 部门
    dept = DepartmentRecord(name="研发中心", leader_id=None, sort_order=0)
    db_session.add(dept)
    await db_session.flush()

    # 角色
    admin_role = RoleRecord(
        role_name="系统管理员",
        role_code="system_admin",
        description="全权限",
    )
    db_session.add(admin_role)
    await db_session.flush()

    # 17 权限码
    db_session.add_all([
        RolePermissionRecord(
            role_id=admin_role.id, permission_code=code, permission_type="api"
        )
        for code in ALL_PERMISSION_CODES
    ])

    # admin 用户
    admin_user = UserRecord(
        username="admin",
        password_hash=fast_hasher.hash("Admin@123"),
        display_name="系统管理员",
        department_id=dept.id,
        status=1,
    )
    db_session.add(admin_user)
    await db_session.flush()

    # user_roles
    db_session.add(UserRoleRecord(user_id=admin_user.id, role_id=admin_role.id))

    await db_session.commit()
    return {"user_id": admin_user.id, "username": "admin", "password": "Admin@123"}


@pytest_asyncio.fixture
async def seeded_disabled_user(db_session, fast_hasher):
    """status=0 的停用用户。"""
    dept = DepartmentRecord(name="测试部", leader_id=None, sort_order=0)
    db_session.add(dept)
    await db_session.flush()
    user = UserRecord(
        username="disabled",
        password_hash=fast_hasher.hash("Pass@1234"),
        display_name="停用账号",
        department_id=dept.id,
        status=0,
    )
    db_session.add(user)
    await db_session.commit()
    return {"user_id": user.id, "username": "disabled", "password": "Pass@1234"}


@pytest_asyncio.fixture
async def seeded_regular_user(db_session, fast_hasher):
    """regular_user：仅 4 权限码（ai:chat / knowledge:read / faq:read / gap:read）。"""
    dept = DepartmentRecord(name="业务部", leader_id=None, sort_order=0)
    db_session.add(dept)
    await db_session.flush()

    role = RoleRecord(
        role_name="普通用户",
        role_code="regular_user",
        description="仅 AI + 知识查询",
    )
    db_session.add(role)
    await db_session.flush()

    for code in (
        PermissionCode.AI_CHAT,
        PermissionCode.KNOWLEDGE_READ,
        PermissionCode.FAQ_READ,
        PermissionCode.GAP_READ,
    ):
        db_session.add(
            RolePermissionRecord(role_id=role.id, permission_code=code, permission_type="api")
        )

    user = UserRecord(
        username="alice",
        password_hash=fast_hasher.hash("Alice@123"),
        display_name="Alice",
        department_id=dept.id,
        status=1,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRoleRecord(user_id=user.id, role_id=role.id))
    await db_session.commit()
    return {"user_id": user.id, "username": "alice", "password": "Alice@123"}


# ── Token fixtures（绕过 /login，直接签发） ─────────────────────────────


@pytest.fixture
def jwt_issuer() -> JWTIssuer:
    return JWTIssuer(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expire_minutes=settings.jwt_expire_minutes,
    )


@pytest.fixture
def admin_token(jwt_issuer, seeded_admin):
    token, _ = jwt_issuer.issue(
        user_id=seeded_admin["user_id"],
        username=seeded_admin["username"],
        role_codes=["system_admin"],
    )
    return token


@pytest.fixture
def regular_user_token(jwt_issuer, seeded_regular_user):
    token, _ = jwt_issuer.issue(
        user_id=seeded_regular_user["user_id"],
        username=seeded_regular_user["username"],
        role_codes=["regular_user"],
    )
    return token


@pytest.fixture
def expired_token(jwt_issuer, seeded_admin):
    """生成已过期的 token（expire_minutes=-1）。"""
    expired = JWTIssuer(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expire_minutes=-1,
    )
    token, _ = expired.issue(
        user_id=seeded_admin["user_id"],
        username=seeded_admin["username"],
        role_codes=["system_admin"],
    )
    return token


__all__ = [
    "async_engine",
    "db_session",
    "async_client",
    "fake_redis",
    "fast_hasher",
    "seeded_admin",
    "seeded_disabled_user",
    "seeded_regular_user",
    "jwt_issuer",
    "admin_token",
    "regular_user_token",
    "expired_token",
]