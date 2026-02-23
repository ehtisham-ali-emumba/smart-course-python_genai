"""Core service API routes."""

from fastapi import APIRouter

from core_service.config import core_settings

router = APIRouter(prefix="/core", tags=["core"])


@router.get("/health")
async def core_health() -> dict:
    """Core service health endpoint (routed via API gateway)."""
    return {
        "status": "ok",
        "service": "core-service",
        "capabilities": ["workflow-orchestration", "event-bridge", "temporal"],
    }


@router.get("/workflows/temporal")
async def temporal_workflow_status() -> dict:
    """Temporal workflow configuration status."""
    return {
        "enabled": True,
        "status": "configured",
        "message": "Temporal workflow engine is active.",
        "temporal_host": core_settings.TEMPORAL_HOST,
        "temporal_namespace": core_settings.TEMPORAL_NAMESPACE,
        "task_queue": core_settings.TEMPORAL_TASK_QUEUE,
        "workflows": ["EnrollmentWorkflow"],
        "activities": [
            "fetch_user_details",
            "validate_user_for_enrollment",
            "fetch_course_details",
            "initialize_course_progress",
            "fetch_course_modules",
            "send_enrollment_welcome_email",
            "send_in_app_notification",
        ],
    }


@router.get("/workflows/enrollment/info")
async def enrollment_workflow_info() -> dict:
    """Information about the enrollment workflow."""
    return {
        "workflow_name": "EnrollmentWorkflow",
        "trigger": "Kafka event: enrollment.created",
        "steps": [
            {
                "order": 1,
                "name": "validate_user",
                "activity": "validate_user_for_enrollment",
                "service": "user-service",
                "critical": True,
            },
            {
                "order": 2,
                "name": "fetch_user_details",
                "activity": "fetch_user_details",
                "service": "user-service",
                "critical": False,
            },
            {
                "order": 3,
                "name": "fetch_course_details",
                "activity": "fetch_course_details",
                "service": "course-service",
                "critical": False,
            },
            {
                "order": 4,
                "name": "initialize_progress",
                "activity": "initialize_course_progress",
                "service": "course-service",
                "critical": False,
            },
            {
                "order": 5,
                "name": "send_welcome_email",
                "activity": "send_enrollment_welcome_email",
                "service": "notification-service",
                "critical": False,
            },
            {
                "order": 6,
                "name": "send_in_app_notification",
                "activity": "send_in_app_notification",
                "service": "notification-service",
                "critical": False,
            },
        ],
    }

