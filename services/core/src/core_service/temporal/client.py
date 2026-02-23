"""Temporal client singleton for starting workflows."""

import logging

from temporalio.client import Client

from core_service.config import core_settings

logger = logging.getLogger(__name__)

_temporal_client: Client | None = None


async def get_temporal_client() -> Client:
    """Get or create the Temporal client singleton."""
    global _temporal_client
    if _temporal_client is None:
        logger.info(
            "Connecting to Temporal at %s namespace=%s",
            core_settings.TEMPORAL_HOST,
            core_settings.TEMPORAL_NAMESPACE,
        )
        _temporal_client = await Client.connect(
            core_settings.TEMPORAL_HOST,
            namespace=core_settings.TEMPORAL_NAMESPACE,
        )
        logger.info("Temporal client connected successfully")
    return _temporal_client


async def close_temporal_client() -> None:
    """Close the Temporal client connection."""
    global _temporal_client
    if _temporal_client is not None:
        # Note: temporalio client doesn't have explicit close,
        # but we clear the reference for clean shutdown
        _temporal_client = None
        logger.info("Temporal client reference cleared")
