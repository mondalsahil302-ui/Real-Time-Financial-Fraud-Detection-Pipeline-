# syntax=docker/dockerfile:1
# Multi-stage production build for Real-Time Financial Fraud Detection Platform API

# ============================================================================
# Stage 1: Build & Wheel Compilation
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY docker/requirements-api.txt ./requirements.txt

# Create appuser home for user install
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

USER appuser
ENV PATH="/home/appuser/.local/bin:${PATH}"

RUN pip install --no-cache-dir --user --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# ============================================================================
# Stage 2: Final Minimal Runtime Image
# ============================================================================
FROM python:3.11-slim AS runtime

LABEL maintainer="Fraud Engineering Team" \
      version="1.0.0" \
      description="Production FastAPI Control Center & Fraud Detection Service"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app" \
    PORT=8001 \
    BACKEND_HOST="0.0.0.0" \
    BACKEND_PORT=8001 \
    PATH="/home/appuser/.local/bin:${PATH}"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user matching builder
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Copy installed packages from builder stage
COPY --from=builder --chown=appuser:appgroup /home/appuser/.local /home/appuser/.local

# Copy application source directories
COPY --chown=appuser:appgroup backend/ /app/backend/
COPY --chown=appuser:appgroup models/ /app/models/
COPY --chown=appuser:appgroup database/ /app/database/
COPY --chown=appuser:appgroup rag/ /app/rag/
COPY --chown=appuser:appgroup fraud_rag_knowledge_base/ /app/fraud_rag_knowledge_base/
COPY --chown=appuser:appgroup streaming/ /app/streaming/
COPY --chown=appuser:appgroup producer/ /app/producer/
COPY --chown=appuser:appgroup tools/ /app/tools/

# Create runtime directories for data, vector db, logs
RUN mkdir -p /app/backend/data /app/vector_db /app/checkpoints /app/logs && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8001

HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:8001/api/health || exit 1

ENTRYPOINT ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8001"]

