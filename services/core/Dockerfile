FROM python:3.12-slim

WORKDIR /app

COPY services/core/pyproject.toml .
COPY services/core/src/ ./src/
RUN pip install --no-cache-dir .
ENV PYTHONPATH=/app/src

CMD ["python", "-m", "core_service.consumers.event_bridge"]
