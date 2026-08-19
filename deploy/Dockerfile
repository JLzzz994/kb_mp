# kb_mp FastAPI 镜像
# 多阶段构建：builder 装依赖 → runtime 仅保留代码

FROM python:3.12-slim AS builder

# 系统依赖（psycopg/bcrypt/python-docx 等需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 装依赖（先 copy lock 文件，最大化层缓存）
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv export --format requirements-txt --no-hashes -o requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# ── runtime ─────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# 复制依赖
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制代码
COPY app/ ./app/
COPY main.py ./
COPY alembic.ini ./alembic.ini 2>/dev/null || true
COPY alembic/ ./alembic/ 2>/dev/null || true
COPY scripts/ ./scripts/ 2>/dev/null || true

# 静态文件 / 数据挂载点
RUN mkdir -p /app/storage/uploads

# 非 root 用户
RUN useradd -m -u 1000 kb_mp && chown -R kb_mp:kb_mp /app
USER kb_mp

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

# 健康检查使用 Python 而非 curl（Alpine 不一定有 curl）
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
