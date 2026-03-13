"""Temporal client singleton — reusable across any service."""

import logging
from temporalio.client import Client

logger = logging.getLogger(__name__)

_temporal_client: Client | None = None


async def get_temporal_client(
    host: str,
    namespace: str = "default",
) -> Client:
    """Get or create the Temporal client singleton.

    Args:
        host: Temporal server address (e.g. "temporal:7233").
        namespace: Temporal namespace (default "default").

    Returns:
        Connected Temporal Client instance (singleton).
    """
    global _temporal_client
    if _temporal_client is None:
        logger.info("Connecting to Temporal at %s namespace=%s", host, namespace)
        _temporal_client = await Client.connect(host, namespace=namespace)
        logger.info("Temporal client connected successfully")
    return _temporal_client


async def close_temporal_client() -> None:
    """Clear the Temporal client reference for clean shutdown."""
    global _temporal_client
    if _temporal_client is not None:
        _temporal_client = None
        logger.info("Temporal client reference cleared")
