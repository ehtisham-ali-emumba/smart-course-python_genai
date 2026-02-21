FROM python:3.12-slim

WORKDIR /app

COPY services/core/pyproject.toml .
COPY services/core/src/ ./src/
RUN pip install --no-cache-dir .
ENV PYTHONPATH=/app/src

# Core is a library; no standalone process. Placeholder for potential future use.
CMD ["sleep", "infinity"]
