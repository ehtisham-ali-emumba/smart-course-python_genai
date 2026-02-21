from notification_service.mocks import MockNotificationService
from notification_service.worker import celery_app

mock_notification = MockNotificationService()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.notification.create_in_app_notification",
)
def create_in_app_notification(
    self,
    user_id: int,
    title: str,
    message: str,
    notification_type: str = "system",
):
    """Create an in-app notification for a user.

    In production: write to a notifications DB table and push via WebSocket.
    """
    try:
        return mock_notification.create(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
