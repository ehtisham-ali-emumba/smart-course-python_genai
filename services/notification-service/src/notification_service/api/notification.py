from datetime import datetime

from fastapi import APIRouter, Header, HTTPException

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
from notification_service.services.notification import NotificationService
from notification_service.worker import celery_app

router = APIRouter()
notification_service = NotificationService()

EMAIL_QUEUE = "email_queue"
NOTIFICATION_QUEUE = "notification_queue"


@router.post("/send", response_model=NotificationResponse)
async def send_notification(
    request: SendNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """
    Generic send endpoint. Called by Temporal EnrollmentWorkflow step 6 (in-app notification).
    Enqueues create_in_app_notification when channel is in_app.
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")

    if request.channel == NotificationChannel.IN_APP:
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": str(request.user_id),
                "title": request.title,
                "message": request.message,
                "notification_type": str(request.type),
            },
            queue=NOTIFICATION_QUEUE,
        )

    return NotificationResponse(
        success=True,
        message="Notification task enqueued",
        notification_type=request.type,
        channel=request.channel,
        timestamp=datetime.utcnow(),
    )


@router.post("/enrollment", response_model=NotificationResponse)
async def notify_enrollment(
    request: EnrollmentNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """
    Called by Temporal EnrollmentWorkflow step 5 (welcome email).
    Enqueues:
      1. send_enrollment_confirmation  → email_queue      (only if email provided)
      2. create_in_app_notification    → notification_queue
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")

    # Task 1 — enrollment confirmation email (skip if no email address)
    if request.email:
        celery_app.send_task(
            "notification_service.tasks.email.send_enrollment_confirmation",
            kwargs={
                "student_id": str(request.user_id),
                "course_id": str(request.course_id),
                "course_title": request.course_title,
                "email": request.email,
            },
            queue=EMAIL_QUEUE,
        )

    # Task 2 — in-app notification
    celery_app.send_task(
        "notification_service.tasks.notification.create_in_app_notification",
        kwargs={
            "user_id": str(request.user_id),
            "title": "Enrollment Confirmed!",
            "message": f"You're enrolled in '{request.course_title}'.",
            "notification_type": "enrollment",
        },
        queue=NOTIFICATION_QUEUE,
    )

    return NotificationResponse(
        success=True,
        message="Enrollment notification tasks enqueued",
        notification_type=NotificationType.ENROLLMENT_WELCOME,
        channel=NotificationChannel.EMAIL,
        timestamp=datetime.utcnow(),
    )


@router.post("/course", response_model=NotificationResponse)
async def notify_course_event(
    request: CourseNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle course event notification via notification service."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_course_event(request)


@router.post("/certificate", response_model=NotificationResponse)
async def notify_certificate(
    request: CertificateNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle certificate notification via notification service."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_certificate(request)


@router.post("/progress", response_model=NotificationResponse)
async def notify_progress(
    request: ProgressNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle progress milestone notification via notification service."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_progress(request)
