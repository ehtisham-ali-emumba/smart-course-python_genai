from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


# --- Enums ---

class NotificationChannel(str, Enum):
    """Supported notification delivery channels."""
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"
    SMS = "sms"


class NotificationPriority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationType(str, Enum):
    """Types of notifications the service handles."""
    ENROLLMENT_WELCOME = "enrollment_welcome"
    ENROLLMENT_COMPLETED = "enrollment_completed"
    COURSE_PUBLISHED = "course_published"
    COURSE_ARCHIVED = "course_archived"
    MODULE_COMPLETED = "module_completed"
    CERTIFICATE_ISSUED = "certificate_issued"
    COURSE_REMINDER = "course_reminder"
    USER_REGISTERED = "user_registered"
    GENERIC = "generic"


# --- Request Schemas ---

class SendNotificationRequest(BaseModel):
    """Generic notification send request."""
    user_id: int = Field(..., description="Target user ID")
    type: NotificationType = Field(default=NotificationType.GENERIC, description="Notification type")
    channel: NotificationChannel = Field(default=NotificationChannel.EMAIL, description="Delivery channel")
    priority: NotificationPriority = Field(default=NotificationPriority.NORMAL, description="Priority level")
    title: str = Field(..., min_length=1, max_length=255, description="Notification title")
    message: str = Field(..., min_length=1, description="Notification message body")
    metadata: dict | None = Field(default=None, description="Additional metadata (course_id, enrollment_id, etc.)")


class EnrollmentNotificationRequest(BaseModel):
    """Notification request for enrollment events."""
    user_id: int = Field(..., description="Student user ID")
    course_id: int = Field(..., description="Course ID")
    course_title: str = Field(..., description="Course title")
    enrollment_id: int = Field(..., description="Enrollment ID")
    instructor_name: str = Field(default="", description="Instructor name")


class CourseNotificationRequest(BaseModel):
    """Notification request for course events (published, archived, etc.)."""
    course_id: int = Field(..., description="Course ID")
    course_title: str = Field(..., description="Course title")
    instructor_id: int = Field(..., description="Instructor user ID")
    event: str = Field(..., description="Event type: 'published', 'archived', 'updated'")
    affected_user_ids: list[int] = Field(default_factory=list, description="List of user IDs to notify")


class CertificateNotificationRequest(BaseModel):
    """Notification request when a certificate is issued."""
    user_id: int = Field(..., description="Student user ID")
    course_id: int = Field(..., description="Course ID")
    course_title: str = Field(..., description="Course title")
    certificate_id: int = Field(..., description="Certificate ID")
    certificate_number: str = Field(..., description="Certificate number")
    verification_code: str = Field(..., description="Verification code")


class ProgressNotificationRequest(BaseModel):
    """Notification request for progress milestones."""
    user_id: int = Field(..., description="Student user ID")
    course_id: int = Field(..., description="Course ID")
    course_title: str = Field(..., description="Course title")
    enrollment_id: int = Field(..., description="Enrollment ID")
    module_title: str = Field(default="", description="Completed module title")
    completion_percentage: float = Field(..., ge=0, le=100, description="Current completion percentage")


# --- Response Schemas ---

class NotificationResponse(BaseModel):
    """Standard response for notification requests."""
    success: bool = Field(..., description="Whether the notification was queued/logged successfully")
    message: str = Field(..., description="Human-readable status message")
    notification_type: NotificationType = Field(..., description="Type of notification processed")
    channel: NotificationChannel = Field(default=NotificationChannel.EMAIL, description="Delivery channel used")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Processing timestamp")
