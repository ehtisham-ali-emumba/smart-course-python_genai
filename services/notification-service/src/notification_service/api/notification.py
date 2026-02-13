from fastapi import APIRouter, Header, HTTPException

from notification_service.schemas.notification import (
    CertificateNotificationRequest,
    CourseNotificationRequest,
    EnrollmentNotificationRequest,
    NotificationResponse,
    ProgressNotificationRequest,
    SendNotificationRequest,
)
from notification_service.services.notification import NotificationService

router = APIRouter()
notification_service = NotificationService()


@router.post("/send", response_model=NotificationResponse)
async def send_notification(
    request: SendNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Send a generic notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.send_notification(request)


@router.post("/enrollment", response_model=NotificationResponse)
async def notify_enrollment(
    request: EnrollmentNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle enrollment notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_enrollment(request)


@router.post("/course", response_model=NotificationResponse)
async def notify_course_event(
    request: CourseNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle course event notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_course_event(request)


@router.post("/certificate", response_model=NotificationResponse)
async def notify_certificate(
    request: CertificateNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle certificate notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_certificate(request)


@router.post("/progress", response_model=NotificationResponse)
async def notify_progress(
    request: ProgressNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle progress milestone notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_progress(request)
