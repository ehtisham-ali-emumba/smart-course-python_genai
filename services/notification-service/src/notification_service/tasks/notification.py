"""Notification Celery tasks for notification service."""

from notification_service.mocks import MockNotificationService
from notification_service.worker import celery_app


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.notification.create_in_app_notification",
)
def create_in_app_notification(
    self, user_id: int, title: str, message: str, notification_type: str = "system"
):
    """
    Triggered by: Any event that needs in-app notification
    Purpose: Create a notification visible in user's dashboard

    Types:
    - welcome: New user welcome
    - enrollment: Enrollment status changes
    - progress: Course progress milestones
    - certificate: Certificate issued
    - course_published: Instructor's course went live
    - system: System announcements
    """
    try:
        return MockNotificationService.create(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task(
    bind=True, max_retries=3, name="notification_service.tasks.notification.send_push_notification"
)
def send_push_notification(self, user_id: int, title: str, body: str, data: dict = None):
    """
    Future: Send push notification to mobile device
    Requires: FCM/APNs integration
    """
    try:
        push_payload = data or {}
        return MockNotificationService.create(
            user_id=user_id,
            title=f"[Push] {title}",
            message=f"{body}\nData: {push_payload}",
            notification_type="push",
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
