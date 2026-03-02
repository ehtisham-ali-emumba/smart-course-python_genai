"""Temporal workflows for core-service."""

from core_service.temporal.workflows.enrollment_workflow import (
    EnrollmentWorkflow,
    EnrollmentWorkflowInput,
    EnrollmentWorkflowOutput,
)
from core_service.temporal.workflows.course_publish_workflow import (
    CoursePublishWorkflow,
    CoursePublishWorkflowInput,
    CoursePublishWorkflowOutput,
)

# All workflows that need to be registered with the worker
ALL_WORKFLOWS = [
    EnrollmentWorkflow,
    CoursePublishWorkflow,
]

__all__ = [
    "EnrollmentWorkflow",
    "EnrollmentWorkflowInput",
    "EnrollmentWorkflowOutput",
    "CoursePublishWorkflow",
    "CoursePublishWorkflowInput",
    "CoursePublishWorkflowOutput",
    "ALL_WORKFLOWS",
]
