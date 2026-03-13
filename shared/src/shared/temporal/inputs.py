"""Temporal workflow input/output dataclasses shared across services."""

from dataclasses import dataclass, field


# ── Enrollment Workflow ──────────────────────────────────────


@dataclass
class EnrollmentWorkflowInput:
    """Input for the EnrollmentWorkflow."""

    student_id: int
    course_id: int
    course_title: str
    student_email: str
    payment_amount: float = 0.0
    enrollment_source: str = "web"


@dataclass
class EnrollmentWorkflowOutput:
    """Output from the EnrollmentWorkflow."""

    workflow_id: str
    student_id: int
    course_id: int
    success: bool
    steps_completed: list[str] = field(default_factory=list)
    steps_failed: list[str] = field(default_factory=list)
    error_message: str | None = None


# ── Course Publish Workflow ──────────────────────────────────


@dataclass
class CoursePublishWorkflowInput:
    """Input for the CoursePublishWorkflow."""

    course_id: int
    instructor_id: int
    course_title: str


@dataclass
class CoursePublishWorkflowOutput:
    """Output from the CoursePublishWorkflow."""

    workflow_id: str
    course_id: int
    instructor_id: int
    success: bool
    steps_completed: list[str] = field(default_factory=list)
    steps_failed: list[str] = field(default_factory=list)
    error_message: str | None = None
