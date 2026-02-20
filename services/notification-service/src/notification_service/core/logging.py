import logging
import sys

import structlog
from notification_service.config import settings

NOISY_LOGGERS = (
    "aiokafka",
    "aiokafka.conn",
    "aiokafka.consumer",
    "aiokafka.consumer.fetcher",
    "aiokafka.consumer.group_coordinator",
    "aiokafka.consumer.subscription_state",
    "kafka",
    "kafka.conn",
    "kafka.consumer",
    "asyncio",
    "urllib3",
    "httpcore",
    "httpx",
)


def setup_logging() -> None:
    """Configure structured logging for the notification service."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(component=name)
    return logger
