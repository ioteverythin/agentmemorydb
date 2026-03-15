# ═══════════════════════════════════════════════════════════
# AgentMemoryDB — Production-Ready Multi-Stage Dockerfile
# ═══════════════════════════════════════════════════════════

# ── Stage 1: Frontend ───────────────────────────────────────
FROM node:20-slim AS frontend

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts 2>/dev/null || npm install
COPY frontend/ .
RUN npm run build

# ── Stage 2: Python Builder ─────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

# Install into a virtual-env so we can COPY it to the final stage
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[metrics,sentence-transformers]"

# ── Stage 2: Runtime ───────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="AgentMemoryDB Contributors"
LABEL org.opencontainers.image.source="https://github.com/agentmemorydb/agentmemorydb"
LABEL org.opencontainers.image.description="SQL-native, auditable memory backend for agentic AI"

# Runtime-only system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    SENTENCE_TRANSFORMERS_HOME=/opt/st_models

# Pre-download model during build — avoids slow first-request download
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2', cache_folder='/opt/st_models')"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/code \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid appuser --create-home appuser

WORKDIR /code

# Copy source code
COPY alembic/ alembic/
COPY alembic.ini .
COPY app/ app/

# Copy pre-built frontend into the static directory
COPY --from=frontend /frontend/dist/ app/static/explorer/

# Copy entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Static files need to be readable
RUN chown -R appuser:appuser /code

USER appuser

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8100/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]
