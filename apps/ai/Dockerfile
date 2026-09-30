# OntologyAI Python AI Worker
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install all dependencies into a virtual environment
RUN uv venv /app/.venv && \
    UV_LINK_MODE=copy uv pip install --no-cache .

# ─────────────────────────────────────────────────────
# Runtime Stage
# ─────────────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Install a shell that activates the venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy source
COPY src/ src/

EXPOSE 3001 8081

# The worker serves its own health endpoint (src/worker.py::_serve_health).
# The previous compose healthcheck shelled out to `pg_isready`, which is not
# installed in this image, so it could never pass.
#   :8081/health        liveness  — process is up
#   :8081/health/ready  readiness — Temporal connected, registry loaded
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8081/health/ready || exit 1

CMD ["python", "-m", "src.worker"]
