FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only pyproject.toml first for better caching
COPY pyproject.toml .

# Install dependencies first (without the package itself)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    sqlalchemy>=2.0.25 \
    asyncpg>=0.29.0 \
    psycopg2-binary>=2.9.9 \
    redis>=5.0.0 \
    python-jose[cryptography]>=3.3.0 \
    bcrypt>=4.0.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    email-validator>=2.1.0 \
    python-multipart>=0.0.6 \
    httpx>=0.26.0 \
    opentelemetry-api>=1.22.0 \
    opentelemetry-sdk>=1.22.0 \
    opentelemetry-instrumentation-fastapi>=0.43b0 \
    opentelemetry-instrumentation-sqlalchemy>=0.43b0 \
    prometheus-client>=0.19.0 \
    structlog>=24.1.0

# Copy application code
COPY src/ ./src/

# Install the package in editable mode
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src:/app
EXPOSE 8001

CMD ["uvicorn", "user_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
