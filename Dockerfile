# ==============================================================================
# Vajra-Kavach: Air-Gapped Multi-Stage Dockerfile
# All dependencies & assets are bundled during build; runs with network_mode: "none".
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Dependency Builder (Online during docker build)
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install compilation tools needed for C-extensions (cffi, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest
COPY requirements.txt .

# Create wheelhouse and download all dependencies locally
RUN pip install --upgrade pip setuptools wheel && \
    pip download --dest /wheelhouse -r requirements.txt --prefer-binary

# Create virtual environment and install strictly from local wheelhouse
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-index --find-links=/wheelhouse -r requirements.txt

# ------------------------------------------------------------------------------
# Stage 2: Air-Gapped Runner (100% Offline Runtime)
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runner

# Security hardening: Create non-root unprivileged service account
RUN groupadd -g 10001 vajra && \
    useradd -u 10001 -g vajra -m -s /bin/bash vajra

WORKDIR /app

# Copy virtual environment and wheelhouse from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /wheelhouse /app/wheelhouse

# Copy application source, assets, and config
COPY --chown=vajra:vajra vajra /app/vajra
COPY --chown=vajra:vajra assets /app/assets
COPY --chown=vajra:vajra config /app/config
COPY --chown=vajra:vajra scripts /app/scripts
COPY --chown=vajra:vajra main.py /app/main.py
COPY --chown=vajra:vajra raksha.toml /app/raksha.toml
COPY --chown=vajra:vajra requirements.txt /app/requirements.txt
COPY --chown=vajra:vajra .env.example /app/.env

# Create input/output mount points with appropriate ownership
RUN mkdir -p /app/input /app/output /app/data && \
    chown -R vajra:vajra /app

# Enforce strict offline air-gap environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OFFLINE_MODE=true \
    RAKSHA_SECRET=practice \
    RAKSHAK_POLICY=/app/config/policy.yaml \
    SQLITE_DB_PATH=/app/data/vajra_records.db

# Drop to non-root user
USER vajra

# Standard entrypoint for Track 3: Secret Wards
ENTRYPOINT ["python", "main.py"]
CMD ["--input", "/app/input", "--output", "/app/output"]
