"""Temporal worker that executes workflows and activities."""

import asyncio
import logging
import sys

from temporalio.client import Client
from temporalio.worker import Worker

from core_service.config import core_settings
from core_service.temporal.workflows import ALL_ACTIVITIES, ALL_WORKFLOWS

logger = logging.getLogger(__name__)


def _log(msg: str) -> None:
    """Log to stderr for visibility in Docker."""
    print(msg, file=sys.stderr, flush=True)


async def run_worker() -> None:
    """
    Run the Temporal worker that executes workflows and activities.

    The worker:
    1. Connects to Temporal server
    2. Polls the task queue for work
    3. Executes workflows and activities
    4. Reports results back to Temporal
    """
    _log(
        f"[core-service] Temporal worker starting | "
        f"host={core_settings.TEMPORAL_HOST} "
        f"namespace={core_settings.TEMPORAL_NAMESPACE} "
        f"task_queue={core_settings.TEMPORAL_TASK_QUEUE}"
    )

    # Connect to Temporal
    client = await Client.connect(
        core_settings.TEMPORAL_HOST,
        namespace=core_settings.TEMPORAL_NAMESPACE,
    )

    _log("[core-service] Connected to Temporal server")

    # Create and run worker
    worker = Worker(
        client,
        task_queue=core_settings.TEMPORAL_TASK_QUEUE,
        workflows=ALL_WORKFLOWS,
        activities=ALL_ACTIVITIES,
    )

    _log(
        f"[core-service] Worker registered | "
        f"workflows={[w.__name__ for w in ALL_WORKFLOWS]} "
        f"activities={[a.__name__ for a in ALL_ACTIVITIES]}"
    )

    # Run the worker (blocks until shutdown)
    await worker.run()


async def run_worker_with_retry(max_retries: int = 10) -> None:
    """Run worker with exponential backoff retry."""
    attempt = 0
    max_delay = 30

    while True:
        try:
            await run_worker()
            break
        except asyncio.CancelledError:
            _log("[core-service] Worker shutdown requested")
            raise
        except Exception as e:
            attempt += 1
            if attempt > max_retries:
                _log(f"[core-service] Worker failed after {max_retries} attempts")
                raise

            delay = min(2**attempt, max_delay)
            _log(
                f"[core-service] Worker error (attempt {attempt}/{max_retries}), "
                f"retry in {delay}s: {e!r}"
            )
            await asyncio.sleep(delay)
