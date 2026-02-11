FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ ./src/
RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app/src:/app
EXPOSE 8001

CMD ["uvicorn", "user_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
