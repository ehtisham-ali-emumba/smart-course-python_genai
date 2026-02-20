class Topics:
    """Kafka topic name constants — single source of truth across all services."""

    USER = "user.events"
    COURSE = "course.events"
    ENROLLMENT = "enrollment.events"
    PROGRESS = "progress.events"
    NOTIFICATION = "notification.events"

    ALL = [USER, COURSE, ENROLLMENT, PROGRESS, NOTIFICATION]
