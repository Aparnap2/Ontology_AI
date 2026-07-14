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

EXPOSE 3001

CMD ["python", "-m", "src.worker"]
