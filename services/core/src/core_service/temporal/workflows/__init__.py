"""Temporal workflows for core-service.

Each workflow lives in its own sub-package alongside its activities.
This module aggregates ALL_WORKFLOWS and ALL_ACTIVITIES so the worker
only needs to import from one place.
"""

from core_service.temporal.workflows.enrollment import (
    EnrollmentWorkflow,
    EnrollmentWorkflowInput,
    EnrollmentWorkflowOutput,
    ALL_ACTIVITIES as _enrollment_activities,
)
from core_service.temporal.workflows.course_publish import (
    CoursePublishWorkflow,
    CoursePublishWorkflowInput,
    CoursePublishWorkflowOutput,
    ALL_ACTIVITIES as _course_publish_activities,
)

# All workflows registered with the Temporal worker
ALL_WORKFLOWS = [
    EnrollmentWorkflow,
    CoursePublishWorkflow,
]

# All activities aggregated from every workflow's activities package
ALL_ACTIVITIES = _enrollment_activities + _course_publish_activities

__all__ = [
    "EnrollmentWorkflow",
    "EnrollmentWorkflowInput",
    "EnrollmentWorkflowOutput",
    "CoursePublishWorkflow",
    "CoursePublishWorkflowInput",
    "CoursePublishWorkflowOutput",
    "ALL_WORKFLOWS",
    "ALL_ACTIVITIES",
]
