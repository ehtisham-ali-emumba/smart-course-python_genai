"""Celery app — stub retained for compatibility.

All tasks (email, notification, certificate) moved to notification-service.
Core event bridge is analytics/logging only. No Celery worker needed.
"""

from celery import Celery

from core_service.config import core_settings

celery_app = Celery(
    "smartcourse",
    broker=core_settings.RABBITMQ_URL,
    backend=core_settings.CELERY_RESULT_BACKEND,
    include=[],  # No tasks — all in notification-service
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
