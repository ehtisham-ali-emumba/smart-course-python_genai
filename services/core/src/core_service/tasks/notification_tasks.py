import logging
import textwrap
from datetime import datetime, timezone

from core_service.providers.rabbitmq.celery_app import celery_app

logger = logging.getLogger(__name__)


class MockNotificationService:
    """Simulated in-app notification service that renders styled cards to logs.

    In production, replace with:
    - PostgreSQL insert into notifications table
    - WebSocket push to connected clients
    - Optional push notification via Firebase/APNs
    """

    @staticmethod
    def create(
        user_id: int,
        title: str,
        message: str,
        notification_type: str = "system",
    ) -> dict:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        tag = notification_type.upper()

        wrapped = textwrap.wrap(message, width=53)
        msg_lines = []
        for i, line in enumerate(wrapped):
            prefix = "Message:  " if i == 0 else "          "
            msg_lines.append(f"   {prefix}{line:<53}")

        msg_block = "\n".join(f"║{line} ║" for line in msg_lines)

        output = f"""
╔══════════════════════════════════════════════════════════════════════╗
║  SMARTCOURSE NOTIFICATION SERVICE (MOCK)       {timestamp}  ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║   [ {tag:<60} ] ║
║                                                                    ║
║   User ID:  {user_id:<55}║
║   Title:    {title:<55}║
{msg_block}
║                                                                    ║
║   Channel:  IN_APP                                                 ║
║   Status:   CREATED (mock -- would write to notifications table)   ║
║                                                                    ║
╚══════════════════════════════════════════════════════════════════════╝"""

        print(output)
        logger.info(
            "Mock notification created | user_id=%d | type=%s | title=%s",
            user_id, notification_type, title,
        )
        return {
            "status": "created_mock",
            "user_id": user_id,
            "type": notification_type,
            "title": title,
        }


mock_notification = MockNotificationService()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="core_service.tasks.notification_tasks.create_in_app_notification",
)
def create_in_app_notification(
    self, user_id: int, title: str, message: str, notification_type: str = "system"
):
    try:
        return mock_notification.create(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
        )
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
