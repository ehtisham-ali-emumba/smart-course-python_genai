FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install core service (Kafka consumer, event schemas)
COPY services/core/ /core/
RUN pip install --no-cache-dir /core

# Copy only pyproject.toml first for better caching
COPY services/notification-service/pyproject.toml .

# Install dependencies first (without the package itself)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    httpx>=0.26.0 \
    structlog>=24.1.0 \
    celery[redis]>=5.3.0

COPY services/notification-service/src/ ./src/

# Install the package in editable mode
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src:/app
EXPOSE 8005

CMD ["uvicorn", "notification_service.main:app", "--host", "0.0.0.0", "--port", "8005"]
