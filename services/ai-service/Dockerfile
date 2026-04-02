FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install shared library
COPY shared/pyproject.toml /tmp/shared/pyproject.toml
COPY shared/src/shared /tmp/shared/src/shared
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir /tmp/shared

# Copy pyproject.toml first for layer caching
COPY services/ai-service/pyproject.toml .

# Copy application source before installing the package
COPY services/ai-service/src/ ./src/

# Install all project dependencies declared in pyproject.toml
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src:/app
EXPOSE 8009

CMD ["uvicorn", "ai_service.main:app", "--host", "0.0.0.0", "--port", "8009"]
