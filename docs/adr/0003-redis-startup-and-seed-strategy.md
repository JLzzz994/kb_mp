# ADR-0003: Redis 启动 fast-fail + seed.py 默认 --reset 幂等策略

## 状态
已决定 (2026-08-19)

## 背景
kb_mp P0 编码依赖 Redis 承载鉴权位图（17 权限码 × 全部用户的缓存）。`docs/specs/p0-tickets/00-pr0-infrastructure.md` 9 项 acceptance criteria 涉及 Redis 配置；`scripts/seed.py` 首次跑需"干净"基线。

## 决策

### 决策 1：Redis 启动 fast-fail
- **lifespan 启动时** 调用 `await redis_client._client.ping()`
- **失败即** `raise RuntimeError("Redis unavailable")` 让 uvicorn 启动失败
- **不做** 进程内 dict fallback
- **理由** 鉴权位图缓存命中失败 = 权限校验不一致 = 安全风险；演示期 docker-compose 一键拉起，不存在"Redis 临时不可用"场景

### 决策 2：seed.py 默认 --reset 幂等
- **无参数**：`seed.py` 仅插入缺失项（3 用户 + 3 角色 + 13 权限码 + 3 部门）；保留用户后续修改
- **`--reset` 参数**：先清表（`TRUNCATE` users / roles / user_roles / role_permissions / departments）后重灌
- **理由** 演示期可能多次运行 seed；覆盖会破坏用户修改；清表可重现场景需要主动选择

## 备选方案

| 决策 | 备选 | 拒绝理由 |
| --- | --- | --- |
| Redis 启动 | B. 进程内 dict fallback | 鉴权位图失效 = 越权访问风险 |
| seed.py  | A. ON DUPLICATE KEY UPDATE 覆盖 | 破坏用户业务修改 |
| seed.py | B. SELECT-then-skip | 种子与业务冲突时无明确行为 |

## 影响

- 概要设计 §6 关键决策（鉴权位图缓存命中失败即失败）
- 概要设计 §11 风险（Redis 启动失败行为）
- PR0 工单 9 acceptance criteria 涉及 lifespan
- `seed.py` 文档与 `.env.example` 需含 `DATABASE_URL` 注入说明

## 关联

- ADR-0001（部署架构，Redis 7 已在中间件列表）
- 风险报告 第二轮回归审计 P2（Redis 鉴权位图 5min TTL 失效窗口）
- docs/specs/p0-tickets/00-pr0-infrastructure.md（PR0 工单）