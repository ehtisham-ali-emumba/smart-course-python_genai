"""Temporal workflows for core-service."""

from core_service.temporal.workflows.enrollment_workflow import (
    EnrollmentWorkflow,
    EnrollmentWorkflowInput,
    EnrollmentWorkflowOutput,
)

# All workflows that need to be registered with the worker
ALL_WORKFLOWS = [
    EnrollmentWorkflow,
]

__all__ = [
    "EnrollmentWorkflow",
    "EnrollmentWorkflowInput",
    "EnrollmentWorkflowOutput",
    "ALL_WORKFLOWS",
]
