"""Kafka topic constants for SmartCourse."""

from enum import Enum


class Topics(str, Enum):
    """Kafka topic names."""

    USER = "user.events"
    COURSE = "course.events"
    ENROLLMENT = "enrollment.events"
    PROGRESS = "progress.events"
    NOTIFICATION = "notification.events"
    CERTIFICATE = "certificate.events"
