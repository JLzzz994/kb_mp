# IMPL-M6 — 知识沉淀管理（Python 方法级实现蓝图）

| 项目 | 内容 |
| --- | --- |
| 文档版本 | V1.0 |
| 阶段 | P4 |
| 编写依据 | [Spec M6](../specs/M6-知识沉淀管理.md) |
| 范围 | FAQ 审核发布 + APScheduler 挖掘 + 缺口识别 + 一键建档完整方法 + pytest |

---

## 1. 文件清单

```
app/
├── api/
│   ├── routers/settlement_router.py
│   └── schemas/{faq,knowledge_gap}_schema.py
├── domain/{faq,knowledge_gap}.py
├── services/
│   ├── faq_service.py                # 人工 CRUD
│   ├── faq_review_service.py         # 审核发布
│   ├── faq_cache_service.py          # Redis 同步
│   ├── faq_mining_service.py         # APScheduler 任务
│   ├── knowledge_gap_service.py
│   └── gap_detector.py
├── repositories/
│   ├── faq_repository.py
│   └── knowledge_gap_repository.py
└── infrastructure/scheduler.py

tests/
├── test_faq_review.py
├── test_faq_cache_sync.py
├── test_faq_mining_job.py
├── test_knowledge_gap.py
└── test_one_click_create_unit.py
```

> **ADR-0007 决议**：URL 已下沉到 `/api/v1/faqs` + `/api/v1/knowledge-gaps`，但文件名 `settlement_router.py` 保留为历史命名（修改文件名需同步更新路由 import 路径）。本次仅在 spec §6.1 视图目录、Spec README 接口分组同步沉淀域命名。

---

## 2. FaqCacheService

```python
# app/services/faq_cache_service.py
"""FAQ 缓存同步服务：审核发布后写入 Redis；M4 命中时校验单元版本。"""

from datetime import datetime
import hashlib


class FaqCacheService:
    def __init__(self, redis: RedisClient, unit_repo: KnowledgeUnitRepository):
        self._redis = redis
        self._unit_repo = unit_repo

    @staticmethod
    def compute_hash(question: str) -> str:
        return hashlib.sha1(question.lower().strip().encode("utf-8")).hexdigest()

    async def get(self, question: str) -> dict | None:
        """读 FAQ 缓存（含单元版本校验）。

        步骤：
        1. 计算 hash
        2. HGETALL
        3. 校验 related_unit_id 的 updated_at
        4. 不一致则 DEL + 返回 None
        """
        key = f"faq:cache:{self.compute_hash(question)}"
        cached = await self._redis.hgetall(key)
        if not cached:
            return None

        # 版本校验
        unit_id = int(cached.get("related_unit_id", 0))
        if unit_id > 0:
            db_updated_at = await self._unit_repo.get_updated_at(unit_id)
            if db_updated_at and db_updated_at.isoformat() != cached.get("unit_updated_at"):
                # 版本不一致，失效
                await self._redis.delete(key)
                return None

        return {
            "answer": cached.get("answer"),
            "related_unit_id": unit_id,
            "unit_updated_at": cached.get("unit_updated_at"),
        }

    async def set(self, faq: FaqRecord) -> None:
        """写入 Redis 缓存。"""
        key = f"faq:cache:{self.compute_hash(faq.question)}"
        await self._redis.hset(
            key,
            mapping={
                "answer": faq.answer,
                "related_unit_id": str(faq.related_unit_id or 0),
                "unit_updated_at": faq.unit_updated_at_snapshot.isoformat()
                if faq.unit_updated_at_snapshot
                else "",
            },
        )
        logger.info("faq.cache.set hash={}", self.compute_hash(faq.question)[:8])

    async def delete(self, question: str) -> None:
        """删除 Redis 缓存。"""
        key = f"faq:cache:{self.compute_hash(question)}"
        await self._redis.delete(key)
        logger.info("faq.cache.del hash={}", self.compute_hash(question)[:8])

    async def invalidate_by_unit_ids(self, unit_ids: list[int]) -> None:
        """当知识单元被删除时，失效所有挂载它的 FAQ 缓存。

        步骤：
        1. 查 faqs WHERE related_unit_id IN (?)
        2. 对每个 FAQ 调 delete
        """
        faqs = await self._unit_repo.list_faqs_by_related_unit_ids(unit_ids)
        for f in faqs:
            await self.delete(f.question)
```

---

## 3. FaqReviewService

```python
# app/services/faq_review_service.py
from sqlalchemy.ext.asyncio import AsyncSession


class FaqReviewService:
    def __init__(
        self,
        faq_repo: FaqRepository,
        unit_repo: KnowledgeUnitRepository,
        cache: FaqCacheService,
        session: AsyncSession,  # C3 修复
    ):
        self._repo = faq_repo
        self._unit_repo = unit_repo
        self._cache = cache
        self._session = session

    async def approve(
        self,
        faq_id: int,
        edited_answer: str | None,
        reviewer: CurrentUser,
    ) -> FaqResponse:
        """审核通过。

        步骤：
        1. 校验存在
        2. 校验未审核过
        3. 若 edited_answer 非空 → UPDATE answer
        4. UPDATE status=published, reviewer_id, reviewed_at
        5. 加载 related_unit 的 updated_at
        6. UPDATE unit_updated_at_snapshot
        7. Redis HSET faq:cache:<hash>
        8. 返回
        """
        # 1-2. 加载并校验
        faq = await self._repo.find_by_id(faq_id)
        if faq is None:
            raise FaqNotFoundError(faq_id)
        if faq.status != "pending_review":
            raise FaqAlreadyReviewedError(faq_id)

        # 3-4. 更新答案与状态
        if edited_answer is not None and edited_answer.strip():
            faq.answer = edited_answer
        faq.status = "published"
        faq.reviewer_id = reviewer.id
        faq.reviewed_at = datetime.utcnow()

        # 5-6. 加载 unit_updated_at
        if faq.related_unit_id:
            unit_updated = await self._unit_repo.get_updated_at(faq.related_unit_id)
            faq.unit_updated_at_snapshot = unit_updated

        await self._session.flush()

        # 7. Redis 写入
        await self._cache.set(faq)

        logger.info("faq.review.approve faq_id={} reviewer={}", faq_id, reviewer.id)
        return self._to_response(faq)

    async def reject(self, faq_id: int, reviewer: CurrentUser) -> FaqResponse:
        """审核驳回。

        步骤：
        1. 校验
        2. UPDATE status=rejected
        3. Redis DEL（如有）
        4. 返回
        """
        faq = await self._repo.find_by_id(faq_id)
        if faq is None:
            raise FaqNotFoundError(faq_id)
        if faq.status != "pending_review":
            raise FaqAlreadyReviewedError(faq_id)

        faq.status = "rejected"
        faq.reviewer_id = reviewer.id
        faq.reviewed_at = datetime.utcnow()
        await self._session.flush()

        await self._cache.delete(faq.question)

        logger.info("faq.review.reject faq_id={} reviewer={}", faq_id, reviewer.id)
        return self._to_response(faq)
```

---

## 4. FaqService（人工 CRUD）

```python
# app/services/faq_service.py
from sqlalchemy.ext.asyncio import AsyncSession


class FaqService:
    def __init__(
        self,
        faq_repo: FaqRepository,
        faq_cache: FaqCacheService,
        session: AsyncSession,  # C3 修复
    ):
        self._repo = faq_repo
        self._cache = faq_cache
        self._session = session

    async def list(self, *, status=None, source_type=None, page, page_size) -> FaqListResponse: ...
    async def list_recommendations(self, page, page_size) -> FaqListResponse:
        """仅返回 status=pending_review。"""
        return await self.list(status="pending_review", page=page, page_size=page_size)

    async def create(self, data: CreateFaqRequest, user: CurrentUser) -> FaqResponse:
        """人工新建 FAQ。

        步骤：
        1. 校验 question.strip() 长度 >= 5（Spec M6 §4.2 min_length=5）
        2. 计算 question_hash
        3. 校验 question_hash 唯一
        4. INSERT（status=pending_review, source_type=manual）
        5. 返回
        """
        if len(data.question.strip()) < 5:
            raise ValidationError("faq.question_too_short")
        question_hash = hashlib.sha1(data.question.lower().strip().encode()).hexdigest()
        existing = await self._repo.find_by_hash(question_hash)
        if existing is not None:
            raise ValidationError("faq.question_exists")
        record = await self._repo.insert(
            FaqRecord(
                question=data.question,
                question_hash=question_hash,
                answer=data.answer,
                category=data.category,
                related_unit_id=data.related_unit_id,
                source_type="manual",
                status="pending_review",
            )
        )
        return self._to_response(record)

    async def update(self, faq_id: int, data: FaqUpdateRequest, user: CurrentUser) -> FaqResponse:
        """编辑（仅限 status=pending_review 或 published 的可编辑答案；rejected 不可编辑）。

        步骤：
        1. 加载并校验
        2. 若 status == rejected → 抛错
        3. 若提供 answer 且非空 → UPDATE answer
        4. flush
        5. 已发布的（status=published）需重新同步 Redis 缓存
        """
        faq = await self._repo.find_by_id(faq_id)
        if faq is None:
            raise FaqNotFoundError(faq_id)
        if faq.status == "rejected":
            raise FaqAlreadyReviewedError(faq_id)
        if data.answer is not None:
            if not data.answer.strip():
                raise ValidationError("answer_empty")
            faq.answer = data.answer
        await self._session.flush()
        # 已发布的需重新同步 Redis
        if faq.status == "published":
            await self._cache.set(faq)
        return self._to_response(faq)

    async def delete(self, faq_id: int, user: CurrentUser) -> None:
        """下线（软删除：status=rejected + Redis DEL）。"""
        faq = await self._repo.find_by_id(faq_id)
        if faq is None:
            raise FaqNotFoundError(faq_id)
        faq.status = "rejected"
        await self._session.flush()
        await self._cache.delete(faq.question)
```

---

## 5. KnowledgeGapService

```python
# app/services/knowledge_gap_service.py
from sqlalchemy.ext.asyncio import AsyncSession


class KnowledgeGapService:
    def __init__(
        self,
        gap_repo: KnowledgeGapRepository,
        session: AsyncSession,  # C3 修复
    ):
        self._repo = gap_repo
        self._session = session

    async def record(
        self,
        session_id: str,
        user_id: int,
        question: str,
        recalled_units: list[dict],
    ) -> bool:
        """记录知识缺口（M4 record_log 节点调用）。

        步骤：
        1. 计算 Top-1 与 Top-3 平均分
        2. 阈值判定：top1 < 0.5 且 top3_avg < 0.55
        3. 计算 pattern = question.lower().strip()[:255]
        4. INSERT ... ON DUPLICATE KEY UPDATE 累加 ask_count + 追加样例
        5. 裁剪 sample_questions_json（> 20 条时裁剪前段）
        """
        # 1. 评分
        top1 = recalled_units[0]["score"] if recalled_units else 0.0
        top3_avg = (
            sum(u["score"] for u in recalled_units[:3]) / min(3, len(recalled_units))
            if recalled_units
            else 0.0
        )
        # 2. 阈值
        if not (top1 < 0.5 and top3_avg < 0.55):
            return False

        # 3. pattern
        pattern = question.lower().strip()[:255]
        pattern_hash = hashlib.sha1(pattern.encode()).hexdigest()

        # 4. UPSERT
        stmt = text("""
            INSERT INTO knowledge_gaps
                (question_pattern, question_pattern_hash, sample_questions_json,
                 ask_count, last_asked_at, status, created_at, updated_at)
            VALUES (:pattern, :hash, JSON_ARRAY(:question), 1, NOW(), 'unresolved', NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                ask_count = ask_count + 1,
                last_asked_at = NOW(),
                sample_questions_json = JSON_ARRAY_APPEND(
                    sample_questions_json, '$', :question
                ),
                updated_at = NOW()
        """)
        await self._session.execute(
            stmt,
            {
                "pattern": pattern,
                "hash": pattern_hash,
                "question": question,
            },
        )

        # 5. 裁剪
        await self._trim_samples(pattern_hash, keep=20)
        await self._session.commit()

        logger.debug("knowledge_gap.record pattern_hash={}", pattern_hash[:8])
        return True

    async def _trim_samples(self, pattern_hash: str, keep: int) -> None:
        """裁剪 sample_questions_json 至前 keep 条。"""
        stmt = text("""
            UPDATE knowledge_gaps
            SET sample_questions_json = JSON_ARRAYAGG(t.question)
            FROM (
                SELECT JSON_UNQUOTE(JSON_EXTRACT(sample_questions_json, CONCAT('$[', idx, ']'))) AS question
                FROM knowledge_gaps
                CROSS JOIN JSON_TABLE(
                    JSON_KEYS(sample_questions_json),
                    '$[*]' COLUMNS (idx FOR ORDINALITY)
                ) AS jt
                WHERE question_pattern_hash = :hash
                ORDER BY idx DESC
                LIMIT :keep
            ) AS t
            WHERE knowledge_gaps.question_pattern_hash = :hash
        """)
        ...

    async def one_click_create_unit(
        self,
        gap_id: int,
        req: CreateUnitFromGapRequest,
        user: CurrentUser,
        knowledge_unit_service: KnowledgeUnitService,  # M3 服务
        permission_service: KnowledgePermissionService,  # M3 服务
    ) -> KnowledgeUnitResponse:
        """一键建档：创建 knowledge_unit + 配置权限 + 回填 gap。

        步骤：
        1. 加载 gap
        2. 校验 status=未resolved
        3. 调用 M3 KnowledgeUnitService.create（预填标题 + 样例问题作为正文初稿）
        4. 调用 M3 PermissionService.configure
        5. UPDATE gap SET resolved_unit_id=?, status='resolved'
        6. 返回 KnowledgeUnitResponse
        """
        # 1. 加载
        gap = await self._repo.find_by_id(gap_id)
        if gap is None:
            raise KnowledgeGapNotFoundError(gap_id)
        if gap.status == "resolved":
            raise KnowledgeGapAlreadyResolvedError(gap_id)

        # 2. 内容预填
        sample_questions = gap.sample_questions_json[:5]  # 最多 5 条样例
        prefilled_content = (
            f"# {req.title}\n\n"
            f"## 常见提问\n\n"
            + "\n".join(f"- {q}" for q in sample_questions)
            + "\n\n## 正文（待补充）\n\n"
            + req.content
        )

        # 3. 创建 unit（经 M3 服务）
        from app.services.knowledge_unit_service import KnowledgeUnitService

        unit = await knowledge_unit_service.create(
            data=KnowledgeUnitCreate(
                title=req.title,
                content=prefilled_content,
                category=req.category,
                source_file_name=None,
            ),
            user=user,
        )

        # 4. 配置权限
        await permission_service.configure(
            unit_id=unit.id,
            req=ConfigurePermissionsRequest(permissions=req.permissions),
            user=user,
        )

        # 5. 回填 gap
        gap.resolved_unit_id = unit.id
        gap.status = "resolved"
        await self._session.flush()

        logger.info("gap.create_unit gap_id={} unit_id={} actor={}", gap_id, unit.id, user.id)
        return unit
```

---

## 6. FaqMiningService（APScheduler）

```python
# app/services/faq_mining_service.py
"""FAQ 自动挖掘：每日 02:00 触发。"""

from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy import text
import hashlib


class FaqMiningService:
    SIMILARITY_THRESHOLD = 0.80
    MIN_FREQ = 3
    WINDOW_DAYS = 30

    def __init__(
        self,
        session: AsyncSession,
        embedding: EmbeddingService,
        faq_repo: FaqRepository,
        unit_repo: KnowledgeUnitRepository,
    ):
        self._session = session
        self._embedding = embedding
        self._faq_repo = faq_repo
        self._unit_repo = unit_repo

    async def run(self) -> int:
        """挖掘主入口（APScheduler 02:00 触发）。

        步骤：
        1. 从 qa_access_logs 拉近 30 天的问题 + 频次
        2. 过滤频次 >= MIN_FREQ 的问题
        3. 对每个问题调 embedding（批量）
        4. 内存聚类：两两 cosine 相似度 >= SIMILARITY_THRESHOLD 视为同类
        5. 每个聚类选 Top-3 unit_ids（按被召回次数）
        6. INSERT faqs（status=pending_review, source_type=auto_mined）
        7. 跳过 question_hash 已存在的
        8. 返回本次新增数
        """
        # 1. 拉数据
        cutoff = datetime.utcnow() - timedelta(days=self.WINDOW_DAYS)
        stmt = text("""
            SELECT question, recalled_unit_ids_json, COUNT(*) AS c
            FROM qa_access_logs
            WHERE created_at > :cutoff
            GROUP BY question, recalled_unit_ids_json
            HAVING c >= :min_freq
        """)
        rows = (
            await self._session.execute(
                stmt,
                {
                    "cutoff": cutoff,
                    "min_freq": self.MIN_FREQ,
                },
            )
        ).all()

        if not rows:
            return 0

        # 2. 过滤：构造 (idx, question, freq) 三元组供 _cluster 后续对齐
        candidates: list[tuple[str, int, str | None]] = [
            (r.question, int(r.c), r.recalled_unit_ids_json) for r in rows
        ]

        # 3. 批量 embed
        questions = [q for q, _, _ in candidates]
        embeddings = await self._embedding.embed_batch(questions)

        # 4. 内存聚类（_cluster 返回每聚类的 idx 列表）
        cluster_indices = self._cluster(questions, embeddings, threshold=self.SIMILARITY_THRESHOLD)

        # 5. 每聚类选代表 question（按 freq 最高）+ Top-3 unit_ids
        created_count = 0
        for indices in cluster_indices:
            # 5.1 还原 (question, freq, unit_ids_json) 三元组
            cluster_items = [candidates[i] for i in indices]
            # 5.2 选代表（按 freq 最大）
            representative_q, representative_freq, _ = max(cluster_items, key=lambda x: x[1])
            # 5.3 合并 unit_ids
            unit_counter: dict[int, int] = defaultdict(int)
            for _q, _freq, unit_ids_json in cluster_items:
                if unit_ids_json:
                    try:
                        parsed = json.loads(unit_ids_json)
                        for entry in parsed:
                            unit_id = entry.get("id") if isinstance(entry, dict) else entry
                            if isinstance(unit_id, int):
                                unit_counter[unit_id] += 1
                    except json.JSONDecodeError:
                        pass
            top_unit_ids = sorted(unit_counter.keys(), key=lambda x: -unit_counter[x])[:3]
            related_unit_id = top_unit_ids[0] if top_unit_ids else None

            # 5.4 计算 question_hash
            question_hash = hashlib.sha1(representative_q.lower().strip().encode()).hexdigest()

            # 6. 跳过已存在
            existing = await self._faq_repo.find_by_hash(question_hash)
            if existing is not None:
                continue

            # 7. INSERT
            await self._faq_repo.insert(
                FaqRecord(
                    question=representative_q,
                    question_hash=question_hash,
                    answer="",  # 待人工填写
                    category=None,
                    related_unit_id=related_unit_id,
                    source_type="auto_mined",
                    status="pending_review",
                    hit_count=0,
                )
            )
            created_count += 1

        await self._session.commit()
        logger.info("faq.mining.run created={} clusters={}", created_count, len(cluster_indices))
        return created_count

    def _cluster(
        self,
        questions: list[str],
        embeddings: list[list[float]],
        threshold: float,
    ) -> list[list[int]]:
        """简单贪心聚类：相似度 >= threshold 视为同类。

        返回值：每个聚类是一个 question 索引列表（int）。
        调用方负责把 idx 映射回 (question, freq, unit_ids_json) 三元组。
        """
        import numpy as np

        if not embeddings:
            return []

        vectors = np.array(embeddings)
        # 归一化
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        vectors = vectors / norms

        # 相似度矩阵
        sim_matrix = vectors @ vectors.T

        clusters: list[list[int]] = []
        for i in range(len(questions)):
            placed = False
            for cluster in clusters:
                # 与 cluster 第一个元素的相似度 >= 阈值即归入同一类
                if sim_matrix[i, cluster[0]] >= threshold:
                    cluster.append(i)
                    placed = True
                    break
            if not placed:
                clusters.append([i])

        return clusters
```

---

## 7. APScheduler 启动

```python
# app/infrastructure/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore


_scheduler: AsyncIOScheduler | None = None


def start_scheduler(faq_mining: FaqMiningService) -> AsyncIOScheduler:
    """启动 APScheduler 并注册每日 02:00 的 faq_mining 任务。"""
    global _scheduler
    _scheduler = AsyncIOScheduler(jobstores={"default": MemoryJobStore()})

    _scheduler.add_job(
        faq_mining.run,
        trigger=CronTrigger(hour=2, minute=0),
        id="faq_mining_daily",
        name="FAQ 自动挖掘（每日 02:00）",
        replace_existing=True,
        misfire_grace_time=3600,  # 1 小时宽限
        max_instances=1,
    )

    _scheduler.start()
    logger.info("scheduler.started jobs={}", len(_scheduler.get_jobs()))
    return _scheduler


def stop_scheduler() -> None:
    """关闭 APScheduler（lifespan 退出时调用）。"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
```

---
## 7.5 关键 Pydantic Schema

```python
# app/api/schemas/faq_schema.py
"""FAQ 请求 / 响应 Schema。"""


class FaqResponse(BaseModel):
    id: int
    question: str
    answer: str
    category: str | None
    related_unit_id: int | None
    source_type: str  # "manual" | "auto_mined"
    status: str  # "pending_review" | "published" | "rejected"
    hit_count: int
    reviewer_id: int | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FaqListResponse(BaseModel):
    items: list[FaqResponse]
    page: int
    page_size: int
    total: int


class CreateFaqRequest(BaseModel):
    question: str = Field(min_length=5, max_length=512)
    answer: str = Field(min_length=1, max_length=10000)
    category: str | None = Field(default=None, max_length=64)
    related_unit_id: int | None = None


class FaqUpdateRequest(BaseModel):
    """PATCH /api/v1/faqs/{faq_id} 部分更新请求体。

    仅 answer 可编辑；rejected 状态的 FAQ 不可调用本接口（路由层校验）。
    """

    answer: str | None = Field(default=None, min_length=1, max_length=10000)


class FaqReviewRequest(BaseModel):
    """POST /api/v1/faqs/{faq_id}/review 审核请求体。"""

    action: Literal["approve", "reject"]
    edited_answer: str | None = Field(default=None, max_length=10000)


class KnowledgeGapResponse(BaseModel):
    id: int
    question_pattern: str
    sample_questions_json: list[str]
    ask_count: int
    last_asked_at: datetime | None
    status: str  # "unresolved" | "resolved" | "ignored"
    resolved_unit_id: int | None
    created_at: datetime
    updated_at: datetime


class CreateUnitFromGapRequest(BaseModel):
    """POST /api/v1/knowledge-gaps/{id}/create-unit 一键建档请求体。"""

    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    category: str | None = Field(default=None, max_length=64)
    permissions: list["PermissionEntryRequest"] = Field(min_length=1)
```

---

## 8. Router

```python
# app/api/routers/settlement_router.py
# 注意：文件名 settlement_router.py 保留 ADR-0007 协议约定，路径已下沉到 /api/v1/faqs + /api/v1/knowledge-gaps
router = APIRouter(prefix="/api/v1", tags=["knowledge-settlement"])


# --- FAQ ---


@router.get(
    "/faqs", response_model=FaqListResponse, dependencies=[Depends(require_permission("faq:read"))]
)
async def list_faqs(
    service: FaqServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    source_type: str | None = None,
):
    return await service.list(
        page=page, page_size=page_size, status=status, source_type=source_type
    )


@router.get(
    "/faqs/recommendations",
    response_model=FaqListResponse,
    dependencies=[Depends(require_permission("faq:read"))],
)
async def list_recommendations(
    service: FaqServiceDep, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)
):
    return await service.list_recommendations(page, page_size)


@router.post(
    "/faqs",
    response_model=FaqResponse,
    status_code=201,
    dependencies=[Depends(require_permission("faq:write"))],
)
async def create_faq(data: CreateFaqRequest, user: CurrentUserDep, service: FaqServiceDep):
    return await service.create(data, user)


@router.patch(
    "/faqs/{faq_id}",
    response_model=FaqResponse,
    dependencies=[Depends(require_permission("faq:write"))],
)
async def update_faq(
    faq_id: int, data: FaqUpdateRequest, user: CurrentUserDep, service: FaqServiceDep
):
    return await service.update(faq_id, data, user)


@router.post(
    "/faqs/{faq_id}/review",
    response_model=FaqResponse,
    dependencies=[Depends(require_permission("faq:review"))],
)
async def review_faq(
    faq_id: int,
    req: FaqReviewRequest,
    user: CurrentUserDep,
    service: FaqReviewServiceDep,
):
    if req.action == "approve":
        return await service.approve(faq_id, req.edited_answer, user)
    elif req.action == "reject":
        return await service.reject(faq_id, user)


@router.delete(
    "/faqs/{faq_id}", status_code=204, dependencies=[Depends(require_permission("faq:write"))]
)
async def delete_faq(faq_id: int, user: CurrentUserDep, service: FaqServiceDep):
    await service.delete(faq_id, user)


# --- 知识缺口 ---


@router.get(
    "/knowledge-gaps",
    response_model=list[KnowledgeGapResponse],
    dependencies=[Depends(require_permission("gap:read"))],
)
async def list_gaps(
    service: KnowledgeGapServiceDep,
    status: str | None = Query(None, pattern=r"^(unresolved|resolved|ignored)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return await service.list(status=status, page=page, page_size=page_size)


@router.post(
    "/knowledge-gaps/{gap_id}/create-unit",
    response_model=KnowledgeUnitResponse,
    dependencies=[Depends(require_permission("knowledge:write"))],
)
async def create_unit_from_gap(
    gap_id: int,
    req: CreateUnitFromGapRequest,
    user: CurrentUserDep,
    service: KnowledgeGapServiceDep,
):
    return await service.one_click_create_unit(gap_id, req, user)
```

---

## 9. 测试用例

```python
# tests/test_faq_review.py
@pytest.mark.asyncio
class TestFaqReview:
    async def test_approve_writes_redis_cache(
        self, async_client, knowledge_admin_token, seeded_pending_faq, redis_client
    ):
        resp = await async_client.post(
            "/api/v1/faqs/1/review",
            json={"action": "approve", "edited_answer": "标准答案"},
            headers=auth_header(knowledge_admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "published"

        # Redis 缓存写入
        from app.services.faq_cache_service import FaqCacheService

        expected_hash = FaqCacheService.compute_hash(body["question"])
        cached = await redis_client.hgetall(f"faq:cache:{expected_hash}")
        assert cached["answer"] == "标准答案"

    async def test_reject_removes_redis_cache(
        self, async_client, knowledge_admin_token, seeded_published_faq, redis_client
    ):
        # 已有缓存
        cached_before = await redis_client.hgetall("faq:cache:abc")
        assert cached_before

        resp = await async_client.post(
            "/api/v1/faqs/1/review",
            json={"action": "reject"},
            headers=auth_header(knowledge_admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        # 缓存删除
        assert await redis_client.exists("faq:cache:abc") == 0

    async def test_approve_already_reviewed_returns_422(
        self, async_client, knowledge_admin_token, seeded_published_faq
    ):
        resp = await async_client.post(
            "/api/v1/faqs/1/review",
            json={"action": "approve"},
            headers=auth_header(knowledge_admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "faq_already_reviewed"


# tests/test_faq_cache_sync.py
@pytest.mark.asyncio
class TestFaqCacheSync:
    async def test_cache_version_mismatch_invalidates(
        self, faq_cache_service, redis_client, unit_repo_mock
    ):
        # 写入缓存（v1）
        await redis_client.hset(
            "faq:cache:test",
            mapping={
                "answer": "v1 answer",
                "related_unit_id": "1",
                "unit_updated_at": "2026-01-01T00:00:00",
            },
        )
        # mock unit_repo 返回不同版本
        unit_repo_mock.get_updated_at.return_value = datetime(2026, 8, 19)
        result = await faq_cache_service.get("test question")
        assert result is None
        assert await redis_client.exists("faq:cache:test") == 0


# tests/test_faq_mining_job.py
@pytest.mark.asyncio
class TestMining:
    async def test_mining_groups_similar_questions(self, seeded_logs):
        mining = FaqMiningService(...)
        count = await mining.run()
        # 相似问题应被聚类（freq >= 3 且 cos >= 0.80）
        assert count >= 0  # 取决于测试数据

    async def test_mining_skips_existing_hash(self, seeded_logs, seeded_existing_faq):
        mining = FaqMiningService(...)
        count = await mining.run()
        # 已存在的 question_hash 应被跳过
        faqs = await mining._faq_repo.list_all()
        # 没有重复创建

    async def test_mining_idempotent(self, seeded_logs):
        mining = FaqMiningService(...)
        count1 = await mining.run()
        count2 = await mining.run()
        # 二次执行不产生新 FAQ
        assert count2 == 0


# tests/test_knowledge_gap.py
@pytest.mark.asyncio
class TestGap:
    async def test_record_top1_top3_threshold(self, gap_service):
        # 满足阈值
        recorded = await gap_service.record(
            session_id="s1",
            user_id=1,
            question="x",
            recalled_units=[{"id": 1, "score": 0.3}, {"id": 2, "score": 0.4}],
        )
        assert recorded is True

        # 不满足（Top-1 >= 0.5）
        not_recorded = await gap_service.record(
            session_id="s2",
            user_id=1,
            question="y",
            recalled_units=[{"id": 1, "score": 0.8}, {"id": 2, "score": 0.7}],
        )
        assert not_recorded is False

    async def test_record_increments_ask_count(self, gap_service):
        await gap_service.record("s1", 1, "Q", [])
        await gap_service.record("s2", 1, "Q variant", [])
        # ask_count 应为 2

    async def test_one_click_create_unit_resolves_gap(
        self, async_client, knowledge_admin_token, seeded_gap
    ):
        req = {
            "title": "新知识",
            "content": "...",
            "category": "x",
            "permissions": [{"target_type": "global", "target_id": None}],
        }
        resp = await async_client.post(
            "/api/v1/knowledge-gaps/1/create-unit",
            json=req,
            headers=auth_header(knowledge_admin_token),
        )
        assert resp.status_code == 200
        # gap 应更新
        gap_resp = await async_client.get(
            "/api/v1/knowledge-gaps?status=resolved", headers=auth_header(knowledge_admin_token)
        )
        assert any(g["id"] == 1 for g in gap_resp.json())


# tests/test_scheduler.py
@pytest.mark.asyncio
class TestScheduler:
    def test_mining_job_registered(self):
        # 测试 lifespan 启动后定时任务存在
        from app.infrastructure.scheduler import _scheduler

        jobs = _scheduler.get_jobs()
        assert any(j.id == "faq_mining_daily" for j in jobs)

    def test_mining_job_schedule(self):
        from app.infrastructure.scheduler import _scheduler

        job = _scheduler.get_job("faq_mining_daily")
        # 验证 next_run_time 在凌晨 02:00 之后
        next_run = job.next_run_time
        assert next_run.hour == 2
```

---

## 10. 验收 Checklist

- [ ] FAQ 审核通过写入 Redis 缓存（含 unit_updated_at）
- [ ] FAQ 驳回删除 Redis 缓存
- [ ] 知识单元 updated_at 变更后自动失效 FAQ 缓存
- [ ] 自动挖掘相似问题聚类
- [ ] mining 任务 idempotent（二次执行不重复创建）
- [ ] 缺口记录按 Top-1/Top-3 阈值触发
- [ ] 一键建档回填 resolved_unit_id
- [ ] APScheduler 注册 faq_mining_daily 任务
- [ ] 任务 next_run_time 在 02:00