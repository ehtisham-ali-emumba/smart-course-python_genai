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
        "capabilities": ["workflow-orchestration", "event-bridge"],
    }


@router.get("/workflows/temporal")
async def temporal_workflow_status() -> dict:
    """Temporal bootstrap placeholder for upcoming implementation."""
    return {
        "enabled": False,
        "status": "not_configured",
        "message": "Temporal workflow engine will be integrated in this service.",
        "temporal_host": core_settings.TEMPORAL_HOST,
        "temporal_namespace": core_settings.TEMPORAL_NAMESPACE,
        "task_queue": core_settings.TEMPORAL_TASK_QUEUE,
    }

