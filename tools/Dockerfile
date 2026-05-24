# Synthesus 2.0 Dockerfile
# Multi-stage build: slim production image

# ---------------------------------------------------------------------------
# Stage 1: Builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
  && rm -rf /var/lib/apt/lists/*

# Copy dependency spec first for cache efficiency
COPY pyproject.toml ./
COPY README.md ./

# Install runtime deps into a prefix
RUN pip install --upgrade pip \
  && pip install --prefix=/install \
    fastapi "uvicorn[standard]" pydantic httpx \
    faiss-cpu numpy scikit-learn scipy \
    python-dotenv rich tenacity

# ---------------------------------------------------------------------------
# Stage 2: Runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

LABEL maintainer="Str8biddness <dakinellegood@gmail.com>"
LABEL description="AIVM Synthesus 2.0 - Dual-Hemisphere Synthetic Intelligence"
LABEL version="2.0.0"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source
COPY api/        ./api/
COPY core/       ./core/
COPY cognitive/  ./cognitive/
COPY ml/         ./ml/
COPY characters/ ./characters/
COPY scripts/    ./scripts/
COPY static/     ./static/
COPY studio/     ./studio/
COPY unpc_engine/ ./unpc_engine/

# Create data volume mount point
RUN mkdir -p /app/data
VOLUME ["/app/data", "/app/characters"]

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SYNTHESUS_DATA_DIR=/app/data \
    SYNTHESUS_CHARACTERS_DIR=/app/characters \
    PORT=5000

# Non-root user for security
RUN useradd -m -u 1001 synthesus
RUN chown -R synthesus:synthesus /app
USER synthesus

EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/v1/health')"

# Start production server
CMD ["uvicorn", "api.production_server:app", \
     "--host", "0.0.0.0", \
     "--port", "5000", \
     "--workers", "2", \
     "--log-level", "info"]
