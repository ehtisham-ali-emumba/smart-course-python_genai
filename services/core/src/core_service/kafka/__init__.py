"""Kafka consumers for core-service."""

from core_service.kafka.enrollment_consumer import run_enrollment_consumer


__all__ = ["run_enrollment_consumer"]
