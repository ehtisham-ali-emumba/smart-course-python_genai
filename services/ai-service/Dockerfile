FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install ffmpeg for video/audio processing
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Install shared library
COPY shared/pyproject.toml /tmp/shared/pyproject.toml
COPY shared/src/shared /tmp/shared/src/shared
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir /tmp/shared

# Copy only pyproject.toml first for better caching
COPY services/ai-service/pyproject.toml .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    motor>=3.3.0 \
    redis>=5.0.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    httpx>=0.26.0 \
    structlog>=24.1.0 \
    openai>=1.40.0 \
    PyMuPDF>=1.24.0 \
    qdrant-client>=1.12.0 \
    langchain-text-splitters>=0.3.0 \
    langgraph>=0.2.0 \
    langchain-core>=0.3.0

COPY services/ai-service/src/ ./src/

# Install the package in editable mode
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src:/app
EXPOSE 8009

CMD ["uvicorn", "ai_service.main:app", "--host", "0.0.0.0", "--port", "8009"]
