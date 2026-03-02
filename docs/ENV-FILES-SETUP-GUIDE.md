# SmartCourse Environment Files Setup Guide

This project now uses:

- one root `.env` for shared infrastructure values
- one `.env` per microservice for service-specific runtime values
- `config.py` in each service as the environment loader (`BaseSettings`)

## 1) Root `.env`

Location:

- project root: `.env`

Purpose:

- shared credentials and infra-level settings used by Docker Compose and multiple services.

Current keys include:

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `REDIS_PASSWORD`
- `MONGO_USER`, `MONGO_PASSWORD`, `MONGO_DB`
- `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`
- `KAFKA_BOOTSTRAP_SERVERS`, `SCHEMA_REGISTRY_URL`
- `RABBITMQ_USER`, `RABBITMQ_PASSWORD`
- `CELERY_RESULT_BACKEND`
- `TEMPORAL_HOST`, `TEMPORAL_DB_USER`, `TEMPORAL_DB_PASSWORD`

## 2) Service `.env` files

Created files:

- `services/user-service/.env`
- `services/course-service/.env`
- `services/notification-service/.env`
- `services/core/.env`
- `services/api-gateway/auth-sidecar/.env`

These provide service-level variables such as:

- database URLs
- redis URLs
- JWT settings
- Kafka/Schema Registry settings
- RabbitMQ/Celery settings
- temporal/task queue/mock settings (core)

## 3) Docker Compose behavior

`docker-compose.yml` was updated to:

- use `env_file` for app services
- remove hardcoded fallback defaults for sensitive/shared credentials
- read required values directly from root `.env`

Each microservice container now loads:

1. root `.env`
2. its own service `.env`

Service `.env` is listed after root `.env`, so service-specific keys can override root keys if needed.

## 4) Keep `config.py` files

`config.py` files were **not deleted** because application code imports them.

What changed:

- hardcoded defaults were removed for runtime keys
- settings now come from environment variables (`.env` / container environment)
- each config keeps `settings = Settings()` (or `core_settings = CoreSettings()`) for compatibility

## 5) Run project

From project root:

```bash
docker compose up --build
```

## 6) Security note

`.env` files are git-ignored by `.gitignore`, so they are not committed by default.

For team sharing, create `.env.example` files without real secrets.
