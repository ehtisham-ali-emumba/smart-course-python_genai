from notification_service.core.logging import get_logger
from notification_service.schemas.notification import (
    CertificateNotificationRequest,
    CourseNotificationRequest,
    EnrollmentNotificationRequest,
    NotificationChannel,
    NotificationResponse,
    NotificationType,
    ProgressNotificationRequest,
    SendNotificationRequest,
)

logger = get_logger("notification_service")


class NotificationService:
    """
    Notification service handling all notification logic.

    Currently logs all notifications. Will be extended to:
    - Send emails via SMTP/SendGrid/SES
    - Send push notifications via Firebase/APNs
    - Queue tasks via Celery + RabbitMQ
    """

    # --- Generic Send ---

    async def send_notification(self, request: SendNotificationRequest) -> NotificationResponse:
        """
        Send a generic notification. Currently logs only.

        In the future, this will route to the appropriate channel handler
        (email, push, in-app, SMS) based on request.channel.
        """
        logger.info(
            "notification_send_requested",
            user_id=request.user_id,
            notification_type=request.type.value,
            channel=request.channel.value,
            priority=request.priority.value,
            title=request.title,
            message_preview=request.message[:100],
            metadata=request.metadata,
        )

        # Future: Route to appropriate channel handler
        # await self._send_email(request) / self._send_push(request) / etc.

        return NotificationResponse(
            success=True,
            message=f"[LOG] Notification '{request.title}' for user {request.user_id} logged via {request.channel.value}",
            notification_type=request.type,
            channel=request.channel,
        )

    # --- Enrollment Notifications ---

    async def notify_enrollment(self, request: EnrollmentNotificationRequest) -> NotificationResponse:
        """
        Handle enrollment welcome notification. Currently logs only.

        Triggered when: enrollment.created event occurs.
        Future behavior: Send welcome email + in-app notification.
        """
        logger.info(
            "enrollment_notification",
            notification_event="enrollment_created",
            user_id=request.user_id,
            course_id=request.course_id,
            course_title=request.course_title,
            enrollment_id=request.enrollment_id,
            instructor_name=request.instructor_name,
            action="would_send_welcome_email",
        )
        logger.info(
            "enrollment_notification",
            notification_event="enrollment_created",
            user_id=request.user_id,
            course_id=request.course_id,
            action="would_create_in_app_notification",
            message=f"You have been enrolled in '{request.course_title}'",
        )

        return NotificationResponse(
            success=True,
            message=f"[LOG] Enrollment notification for user {request.user_id} in course '{request.course_title}' (enrollment #{request.enrollment_id}) logged",
            notification_type=NotificationType.ENROLLMENT_WELCOME,
            channel=NotificationChannel.EMAIL,
        )

    # --- Course Event Notifications ---

    async def notify_course_event(self, request: CourseNotificationRequest) -> NotificationResponse:
        """
        Handle course lifecycle notifications. Currently logs only.

        Triggered when: course.published, course.archived events occur.
        Future behavior:
        - course.published → Email enrolled students, push notification
        - course.archived → Email enrolled students with info
        """
        logger.info(
            "course_notification",
            notification_event=request.event,
            course_id=request.course_id,
            course_title=request.course_title,
            instructor_id=request.instructor_id,
            affected_users_count=len(request.affected_user_ids),
            affected_user_ids=request.affected_user_ids,
            action=f"would_notify_users_about_course_{request.event}",
        )

        notification_type = (
            NotificationType.COURSE_PUBLISHED if request.event == "published"
            else NotificationType.COURSE_ARCHIVED if request.event == "archived"
            else NotificationType.GENERIC
        )

        return NotificationResponse(
            success=True,
            message=f"[LOG] Course '{request.course_title}' {request.event} notification for {len(request.affected_user_ids)} users logged",
            notification_type=notification_type,
            channel=NotificationChannel.EMAIL,
        )

    # --- Certificate Notifications ---

    async def notify_certificate(self, request: CertificateNotificationRequest) -> NotificationResponse:
        """
        Handle certificate issuance notification. Currently logs only.

        Triggered when: certificate.issued event occurs.
        Future behavior: Send congratulatory email with certificate download link.
        """
        logger.info(
            "certificate_notification",
            notification_event="certificate_issued",
            user_id=request.user_id,
            course_id=request.course_id,
            course_title=request.course_title,
            certificate_id=request.certificate_id,
            certificate_number=request.certificate_number,
            verification_code=request.verification_code,
            action="would_send_certificate_email",
            message=f"Congratulations! Your certificate for '{request.course_title}' is ready.",
        )

        return NotificationResponse(
            success=True,
            message=f"[LOG] Certificate notification for user {request.user_id} - cert #{request.certificate_number} for course '{request.course_title}' logged",
            notification_type=NotificationType.CERTIFICATE_ISSUED,
            channel=NotificationChannel.EMAIL,
        )

    # --- Progress Milestone Notifications ---

    async def notify_progress(self, request: ProgressNotificationRequest) -> NotificationResponse:
        """
        Handle progress milestone notification. Currently logs only.

        Triggered when: progress.module_completed event occurs.
        Future behavior: In-app notification for module completion.
        """
        logger.info(
            "progress_notification",
            notification_event="module_completed",
            user_id=request.user_id,
            course_id=request.course_id,
            course_title=request.course_title,
            enrollment_id=request.enrollment_id,
            module_title=request.module_title,
            completion_percentage=request.completion_percentage,
            action="would_send_progress_in_app_notification",
            message=f"Module '{request.module_title}' completed! {request.completion_percentage}% done.",
        )

        return NotificationResponse(
            success=True,
            message=f"[LOG] Progress notification for user {request.user_id} - module '{request.module_title}' completed ({request.completion_percentage}%) in '{request.course_title}' logged",
            notification_type=NotificationType.MODULE_COMPLETED,
            channel=NotificationChannel.IN_APP,
        )

    # --- Private Channel Handlers (Stubs for Future) ---

    async def _send_email(self, to_user_id: int, subject: str, body: str) -> bool:
        """
        Stub: Send email notification.

        Future implementation:
        - Look up user email from User Service (via HTTP or cache)
        - Send via SMTP / SendGrid / AWS SES
        - Queue via Celery for reliability
        """
        logger.info(
            "email_stub",
            to_user_id=to_user_id,
            subject=subject,
            body_preview=body[:100],
            action="email_send_skipped_stub",
        )
        return True

    async def _send_push(self, to_user_id: int, title: str, body: str) -> bool:
        """
        Stub: Send push notification.

        Future implementation:
        - Look up user device tokens
        - Send via Firebase Cloud Messaging / APNs
        """
        logger.info(
            "push_stub",
            to_user_id=to_user_id,
            title=title,
            body_preview=body[:100],
            action="push_send_skipped_stub",
        )
        return True

    async def _send_sms(self, to_user_id: int, message: str) -> bool:
        """
        Stub: Send SMS notification.

        Future implementation:
        - Look up user phone number from User Service
        - Send via Twilio / AWS SNS
        """
        logger.info(
            "sms_stub",
            to_user_id=to_user_id,
            message_preview=message[:100],
            action="sms_send_skipped_stub",
        )
        return True
