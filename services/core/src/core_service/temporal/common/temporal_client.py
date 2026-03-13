"""Temporal client — delegates to shared.temporal for singleton management."""

from shared.temporal.client import (
    get_temporal_client as _shared_get,
    close_temporal_client,
)

from core_service.config import core_settings


async def get_temporal_client():
    """Get the Temporal client using core-service config."""
    return await _shared_get(
        host=core_settings.TEMPORAL_HOST,
        namespace=core_settings.TEMPORAL_NAMESPACE,
    )


# close_temporal_client is re-exported from shared.temporal
__all__ = ["get_temporal_client", "close_temporal_client"]
