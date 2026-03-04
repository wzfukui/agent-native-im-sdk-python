# Multi-stage build for Agent-Native IM Bot
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r agent && useradd -r -g agent agent

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AGENT_MEMORY_DIR=/data/memory \
    AGENT_LOG_DIR=/data/logs

# Create necessary directories
RUN mkdir -p /data/memory /data/logs /app && \
    chown -R agent:agent /data /app

# Copy application
WORKDIR /app
COPY --chown=agent:agent . .

# Switch to non-root user
USER agent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Volume for persistent data
VOLUME ["/data"]

# Run the agent
CMD ["python", "agent.py"]