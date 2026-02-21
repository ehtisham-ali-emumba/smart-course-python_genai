from celery import Celery

from notification_service.config import settings

celery_app = Celery(
    "smartcourse-notifications",
    broker=settings.RABBITMQ_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "notification_service.tasks.email.*": {"queue": "email_queue"},
        "notification_service.tasks.certificate.*": {"queue": "certificate_queue"},
        "notification_service.tasks.notification.*": {"queue": "notification_queue"},
    },
)

celery_app.autodiscover_tasks([
    "notification_service.tasks",
])

# Explicitly import task modules so they are registered (required when worker runs in Docker)
from notification_service.tasks import email, notification, certificate  # noqa: F401, E402
