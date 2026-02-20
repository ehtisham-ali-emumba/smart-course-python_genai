from celery import Celery

from core_service.config import core_settings


def create_celery_app() -> Celery:
    """Factory function for Celery app instance.

    Used by:
    - The Core Service celery worker process
    - Other services via CeleryDispatcher (only needs broker connection)
    """
    app = Celery(
        "smartcourse",
        broker=core_settings.RABBITMQ_URL,
        backend=core_settings.CELERY_RESULT_BACKEND,
        include=[
            "core_service.tasks.email_tasks",
            "core_service.tasks.notification_tasks",
            "core_service.tasks.certificate_tasks",
        ],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_routes={
            "core_service.tasks.email_tasks.*": {"queue": "email_queue"},
            "core_service.tasks.notification_tasks.*": {"queue": "notification_queue"},
            "core_service.tasks.certificate_tasks.*": {"queue": "certificate_queue"},
        },
        task_default_retry_delay=60,
        task_max_retries=3,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )
    return app


celery_app = create_celery_app()
