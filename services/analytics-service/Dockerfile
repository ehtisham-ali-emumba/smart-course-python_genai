FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY shared/pyproject.toml /tmp/shared/pyproject.toml
COPY shared/src/shared /tmp/shared/src/shared
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir /tmp/shared

COPY services/analytics-service/pyproject.toml .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    sqlalchemy>=2.0.25 \
    asyncpg>=0.29.0 \
    psycopg2-binary>=2.9.9 \
    redis>=5.0.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    aiokafka>=0.10.0 \
    prometheus-fastapi-instrumentator>=7.0.2 \
    prometheus-client>=0.19.0 \
    structlog>=24.1.0 \
    alembic>=1.13.0

COPY services/analytics-service/src/ ./src/
COPY services/analytics-service/alembic.ini ./

RUN pip install --no-cache-dir -e .

COPY services/analytics-service/src/analytics_service/alembic/ ./src/analytics_service/alembic/

ENV PYTHONPATH=/app/src:/app
EXPOSE 8007

CMD ["sh", "-c", "alembic upgrade head && uvicorn analytics_service.main:app --host 0.0.0.0 --port 8007"]
