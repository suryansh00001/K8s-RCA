# Multi-stage hardened container for Autonomous AI SRE Agent (K8s-RCA)
# Enforces non-root execution and minimal attack surface

FROM python:3.10-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Final runtime image
FROM python:3.10-slim AS runner

WORKDIR /app

# Create non-root user (Principle of Least Privilege)
RUN groupadd -g 10001 sreagent && \
    useradd -u 10001 -g sreagent -s /bin/bash -m sreagent

# Copy installed Python site-packages from builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy project files
COPY . .
RUN pip install --no-cache-dir -e .

# Security hardening: Read-only application filesystem, non-root user
RUN chown -R sreagent:sreagent /app
USER sreagent

# Expose web dashboard port
EXPOSE 8080

# Default entrypoint starts the Web UI
ENTRYPOINT ["python", "-m", "k8s_rca.cli"]
CMD ["serve", "--port", "8080"]
