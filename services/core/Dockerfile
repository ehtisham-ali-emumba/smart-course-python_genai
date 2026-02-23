FROM python:3.11-slim

WORKDIR /app

# Install shared library used by core-service imports
COPY shared/pyproject.toml /tmp/shared/pyproject.toml
COPY shared/src/shared /tmp/shared/src/shared
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir /tmp/shared

COPY services/core/pyproject.toml .
COPY services/core/src/ ./src/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src:/app
EXPOSE 8006

CMD ["uvicorn", "core_service.main:app", "--host", "0.0.0.0", "--port", "8006"]
