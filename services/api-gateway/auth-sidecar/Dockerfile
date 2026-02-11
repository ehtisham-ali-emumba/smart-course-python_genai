FROM python:3.11-slim

WORKDIR /app

# Copy dependency definition
COPY pyproject.toml .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    python-jose[cryptography]>=3.3.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0

# Copy source code
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src:/app
EXPOSE 8010

CMD ["uvicorn", "auth_sidecar.main:app", "--host", "0.0.0.0", "--port", "8010"]
