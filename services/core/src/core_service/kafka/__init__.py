"""Kafka consumers for core-service."""

from core_service.kafka.enrollment_consumer import run_enrollment_consumer
from core_service.kafka.course_consumer import run_course_consumer

__all__ = ["run_enrollment_consumer", "run_course_consumer"]
