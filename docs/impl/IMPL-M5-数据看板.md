# IMPL-M5 — 数据看板（Python 方法级实现蓝图）

| 项目 | 内容 |
| --- | --- |
| 文档版本 | V1.0 |
| 阶段 | P3 |
| 编写依据 | [Spec M5](../specs/M5-数据看板.md) |
| 范围 | 5 个聚合查询完整方法 + pytest |

---

## 1. 文件清单

```
app/
├── api/
│   ├── routers/dashboard_router.py
│   └── schemas/{dashboard_metric,dashboard_ranking,dashboard_stats}_schema.py
├── services/dashboard_service.py
└── repositories/dashboard_repository.py

tests/test_dashboard.py
```

---

## 2. Repository（聚合查询）

```python
# app/repositories/dashboard_repository.py
"""DashboardRepository：仅做聚合查询，不写。"""
from datetime import datetime, timedelta
from sqlalchemy import select, func, text, desc
from sqlalchemy.ext.asyncio import AsyncSession


class DashboardRepository:
    VALID_RANGES = {7, 30, 90}

    def __init__(self, session: AsyncSession):
        self._session = session

    async def fetch_metrics(self, range_days: int) -> dict:
        """核心 5 项指标。

        SQL:
            SELECT
                COUNT(*),
                COUNT(DISTINCT user_id),
                COALESCE(SUM(total_tokens), 0),
                COALESCE(AVG(response_time_ms), 0)
            FROM qa_access_logs
            WHERE created_at > NOW() - INTERVAL ? DAY

            + SELECT COUNT(*) FROM knowledge_units WHERE status='active'
        """
        if range_days not in self.VALID_RANGES:
            raise InvalidRangeError(range_days)

        cutoff = datetime.utcnow() - timedelta(days=range_days)

        # 1. 主指标
        stmt = text("""
            SELECT
                COUNT(*) AS access_count,
                COUNT(DISTINCT user_id) AS unique_users,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(AVG(response_time_ms), 0) AS avg_response_time_ms
            FROM qa_access_logs
            WHERE created_at > :cutoff
        """)
        result = await self._session.execute(stmt, {"cutoff": cutoff})
        row = result.first()
        if row is None:
            return {
                "access_count": 0,
                "unique_users": 0,
                "total_tokens": 0,
                "avg_response_time_ms": 0.0,
                "unit_count": 0,
            }

        # 2. 单元数
        unit_count_stmt = (
            select(func.count(KnowledgeUnitRecord.id))
            .where(KnowledgeUnitRecord.status == "active")
        )
        unit_count = (await self._session.execute(unit_count_stmt)).scalar_one()

        return {
            "access_count": int(row.access_count),
            "unique_users": int(row.unique_users),
            "total_tokens": int(row.total_tokens),
            "avg_response_time_ms": float(row.avg_response_time_ms),
            "unit_count": int(unit_count),
        }

    async def fetch_question_rankings(self, range_days: int, limit: int = 20) -> list[dict]:
        """常见问题 TOP 榜。

        SQL:
            SELECT question, COUNT(*) AS c, MAX(created_at) AS last_asked_at
            FROM qa_access_logs
            WHERE created_at > NOW() - INTERVAL ? DAY
            GROUP BY question
            ORDER BY c DESC
            LIMIT ?
        """
        cutoff = datetime.utcnow() - timedelta(days=range_days)
        stmt = (
            select(
                QaAccessLogRecord.question,
                func.count().label("c"),
                func.max(QaAccessLogRecord.created_at).label("last_asked_at"),
            )
            .where(QaAccessLogRecord.created_at > cutoff)
            .group_by(QaAccessLogRecord.question)
            .order_by(desc("c"))
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {"question": r.question, "ask_count": int(r.c), "last_asked_at": r.last_asked_at}
            for r in rows
        ]

    async def fetch_unit_rankings(self, range_days: int, limit: int = 20) -> list[dict]:
        """知识热度 TOP 榜（JSON 展开）。

        入参：
        - range_days: 统计窗口（7 / 30 / 90，由调用方校验）
        - limit: TOP 数量上限，默认 20；调用方（service → router）必须显式传入并经 Query 校验。

        SQL:
            SELECT ku.id, ku.unit_code, ku.title, COUNT(*) AS c
            FROM qa_access_logs qa
            JOIN knowledge_units ku ON JSON_CONTAINS(qa.recalled_unit_ids_json, JSON_OBJECT('id', ku.id), '$')
            WHERE qa.created_at > NOW() - INTERVAL ? DAY
            GROUP BY ku.id, ku.unit_code, ku.title
            ORDER BY c DESC
            LIMIT ?
        """
        # 防御：limit 必须为正整数（router 已校验 Query(ge=1, le=100)，但 repo 仍兜底）
        if limit < 1:
            limit = 20
        cutoff = datetime.utcnow() - timedelta(days=range_days)
        stmt = text("""
            SELECT
                ku.id AS unit_id,
                ku.unit_code,
                ku.title,
                COUNT(*) AS access_count
            FROM qa_access_logs qa
            JOIN knowledge_units ku
                ON JSON_CONTAINS(qa.recalled_unit_ids_json, JSON_OBJECT('id', ku.id), '$')
            WHERE qa.created_at > :cutoff
            GROUP BY ku.id, ku.unit_code, ku.title
            ORDER BY access_count DESC
            LIMIT :limit
        """)
        # 注意：limit 经 :limit 命名参数绑定，原生 SQL 不会拼接字面量，无 SQL 注入风险
        result = await self._session.execute(stmt, {"cutoff": cutoff, "limit": limit})
        return [
            {
                "unit_id": int(r.unit_id),
                "unit_code": r.unit_code,
                "title": r.title,
                "access_count": int(r.access_count),
            }
            for r in result.all()
        ]

    async def fetch_token_stats(self, range_days: int) -> list[dict]:
        """Token 趋势（按日分桶）。

        SQL:
            SELECT
                DATE(created_at) AS bucket_date,
                SUM(total_tokens) AS total_tokens,
                SUM(prompt_tokens) AS prompt_tokens,
                SUM(completion_tokens) AS completion_tokens
            FROM qa_access_logs
            WHERE created_at > NOW() - INTERVAL ? DAY
            GROUP BY DATE(created_at)
            ORDER BY bucket_date
        """
        cutoff = datetime.utcnow() - timedelta(days=range_days)
        stmt = (
            select(
                func.date(QaAccessLogRecord.created_at).label("bucket_date"),
                func.sum(QaAccessLogRecord.total_tokens).label("total_tokens"),
                func.sum(QaAccessLogRecord.prompt_tokens).label("prompt_tokens"),
                func.sum(QaAccessLogRecord.completion_tokens).label("completion_tokens"),
            )
            .where(QaAccessLogRecord.created_at > cutoff)
            .group_by(func.date(QaAccessLogRecord.created_at))
            .order_by("bucket_date")
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "bucket_date": r.bucket_date,
                "total_tokens": int(r.total_tokens or 0),
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
            }
            for r in rows
        ]

    async def fetch_response_time_stats(self, range_days: int) -> list[dict]:
        """响应时间趋势（含 avg + p95 + 样本数）。

        SQL:
            SELECT
                DATE(created_at) AS bucket_date,
                AVG(response_time_ms) AS avg,
                COUNT(*) AS sample_count
            FROM qa_access_logs
            WHERE created_at > NOW() - INTERVAL ? DAY
            GROUP BY DATE(created_at)
            ORDER BY bucket_date;

            + P95：先按日分桶取 raw response_time_ms，应用层用 numpy.percentile 计算 P95
            （演示期数据量小，应用层方案比 SQL 窗口函数更直观；数据规模大时切换为 PERCENT_RANK()）。
        """
        cutoff = datetime.utcnow() - timedelta(days=range_days)

        # 1. AVG + sample_count（按日分桶）
        stmt = (
            select(
                func.date(QaAccessLogRecord.created_at).label("bucket_date"),
                func.avg(QaAccessLogRecord.response_time_ms).label("avg"),
                func.count().label("n"),
            )
            .where(QaAccessLogRecord.created_at > cutoff)
            .group_by(func.date(QaAccessLogRecord.created_at))
            .order_by("bucket_date")
        )
        avg_rows = (await self._session.execute(stmt)).all()

        # 2. P95：拉 raw response_time_ms（按日分组）→ 应用层 numpy
        raw_stmt = (
            select(
                func.date(QaAccessLogRecord.created_at).label("bucket_date"),
                QaAccessLogRecord.response_time_ms,
            )
            .where(QaAccessLogRecord.created_at > cutoff)
            .order_by("bucket_date", QaAccessLogRecord.response_time_ms)
        )
        raw_rows = (await self._session.execute(raw_stmt)).all()

        # 3. 内存分桶 → 计算 P95
        buckets: dict[object, list[int]] = {}
        for row in raw_rows:
            buckets.setdefault(row.bucket_date, []).append(int(row.response_time_ms or 0))

        import numpy as np
        result = []
        for avg_row in avg_rows:
            samples = buckets.get(avg_row.bucket_date, [])
            p95 = int(np.percentile(samples, 95)) if samples else 0
            result.append({
                "bucket_date": avg_row.bucket_date,
                "avg_response_time_ms": float(avg_row.avg or 0),
                "p95_response_time_ms": p95,
                "sample_count": int(avg_row.n),
            })
        return result
```

---

## 3. Service

```python
# app/services/dashboard_service.py
class DashboardService:
    def __init__(self, repo: DashboardRepository):
        self._repo = repo

    async def metrics(self, range_days: int) -> MetricsResponse:
        """返回核心 5 项指标。"""
        data = await self._repo.fetch_metrics(range_days)
        return MetricsResponse(
            access_count=data["access_count"],
            unique_users=data["unique_users"],
            unit_count=data["unit_count"],
            total_tokens=data["total_tokens"],
            avg_response_time_ms=data["avg_response_time_ms"],
            range_days=range_days,
        )

    async def question_rankings(self, range_days: int, limit: int = 20) -> list[QuestionRankingItem]:
        items = await self._repo.fetch_question_rankings(range_days, limit)
        return [QuestionRankingItem(**item) for item in items]

    async def unit_rankings(self, range_days: int, limit: int = 20) -> list[UnitRankingItem]:
        items = await self._repo.fetch_unit_rankings(range_days, limit)
        return [UnitRankingItem(**item) for item in items]

    async def token_stats(self, range_days: int) -> list[TokenStatsBucket]:
        items = await self._repo.fetch_token_stats(range_days)
        return [TokenStatsBucket(**item) for item in items]

    async def response_time_stats(self, range_days: int) -> list[ResponseTimeStatsBucket]:
        items = await self._repo.fetch_response_time_stats(range_days)
        return [ResponseTimeStatsBucket(**item) for item in items]
```

---

## 4. Router

```python
# app/api/routers/dashboard_router.py
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=MetricsResponse,
            dependencies=[Depends(require_permission("dashboard:read"))])
async def get_metrics(
    service: DashboardServiceDep,
    range: str = Query("7d", pattern=r"^(7|30|90)d$"),
):
    range_days = int(range.rstrip("d"))
    return await service.metrics(range_days)


@router.get("/rankings/questions", response_model=list[QuestionRankingItem],
            dependencies=[Depends(require_permission("dashboard:read"))])
async def get_question_rankings(
    service: DashboardServiceDep,
    range: str = Query("7d", pattern=r"^(7|30|90)d$"),
    limit: int = Query(20, ge=1, le=100),
):
    range_days = int(range.rstrip("d"))
    return await service.question_rankings(range_days, limit)


@router.get("/rankings/units", response_model=list[UnitRankingItem],
            dependencies=[Depends(require_permission("dashboard:read"))])
async def get_unit_rankings(
    service: DashboardServiceDep,
    range: str = Query("7d", pattern=r"^(7|30|90)d$"),
    limit: int = Query(20, ge=1, le=100),
):
    range_days = int(range.rstrip("d"))
    return await service.unit_rankings(range_days, limit)


@router.get("/stats/tokens", response_model=list[TokenStatsBucket],
            dependencies=[Depends(require_permission("dashboard:read"))])
async def get_token_stats(
    service: DashboardServiceDep,
    range: str = Query("7d", pattern=r"^(7|30)d$"),
):
    range_days = int(range.rstrip("d"))
    return await service.token_stats(range_days)


@router.get("/stats/response-time", response_model=list[ResponseTimeStatsBucket],
            dependencies=[Depends(require_permission("dashboard:read"))])
async def get_response_time_stats(
    service: DashboardServiceDep,
    range: str = Query("7d", pattern=r"^(7|30)d$"),
):
    range_days = int(range.rstrip("d"))
    return await service.response_time_stats(range_days)
```

---

## 5. 测试用例

```python
# tests/test_dashboard.py
@pytest.mark.asyncio
class TestMetrics:

    async def test_metrics_returns_five_indicators(self, async_client, admin_token, seeded_logs):
        resp = await async_client.get(
            "/api/v1/dashboard/metrics?range=7d",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {
            "access_count", "unique_users", "unit_count",
            "total_tokens", "avg_response_time_ms", "range_days",
        }
        assert body["range_days"] == 7

    async def test_metrics_invalid_range_returns_422(self, async_client, admin_token):
        resp = await async_client.get(
            "/api/v1/dashboard/metrics?range=invalid",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 422

    async def test_metrics_regular_user_cannot_access(self, async_client, regular_user_token):
        resp = await async_client.get(
            "/api/v1/dashboard/metrics?range=7d",
            headers=auth_header(regular_user_token),
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestRankings:

    async def test_question_rankings_order_by_count(self, async_client, admin_token, seeded_logs):
        resp = await async_client.get(
            "/api/v1/dashboard/rankings/questions?range=30d",
            headers=auth_header(admin_token),
        )
        body = resp.json()
        # 按 ask_count DESC
        counts = [item["ask_count"] for item in body]
        assert counts == sorted(counts, reverse=True)

    async def test_unit_rankings_dedupes_by_unit(self, async_client, admin_token, seeded_logs):
        resp = await async_client.get(
            "/api/v1/dashboard/rankings/units?range=30d",
            headers=auth_header(admin_token),
        )
        body = resp.json()
        unit_ids = [item["unit_id"] for item in body]
        assert len(unit_ids) == len(set(unit_ids))     # 去重


@pytest.mark.asyncio
class TestStats:

    async def test_token_stats_bucket_by_day(self, async_client, admin_token, seeded_logs):
        resp = await async_client.get(
            "/api/v1/dashboard/stats/tokens?range=7d",
            headers=auth_header(admin_token),
        )
        body = resp.json()
        # 每项含 bucket_date
        assert all("bucket_date" in item for item in body)
        # 桶按日期升序
        dates = [item["bucket_date"] for item in body]
        assert dates == sorted(dates)

    async def test_empty_data_returns_zero(self, async_client, admin_token):
        resp = await async_client.get(
            "/api/v1/dashboard/metrics?range=7d",
            headers=auth_header(admin_token),
        )
        body = resp.json()
        assert body["access_count"] == 0
        assert body["unique_users"] == 0
```

---

## 6. 验收 Checklist

- [ ] 5 项指标正确计算（access_count / unique_users / unit_count / total_tokens / avg_response_time_ms）
- [ ] range 参数校验（仅 7d/30d/90d）
- [ ] TOP 榜按频次正确排序
- [ ] 单位置热度榜正确（去重 + 排序）
- [ ] 趋势图按日期分桶
- [ ] 无数据时返回 0 / 空数组
- [ ] regular_user 无 dashboard:read 权限返回 403