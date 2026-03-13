"""Reusable Temporal client and workflow constants.

NOTE: We intentionally do NOT import from .client here.
The client module imports temporalio.client which is incompatible with
Temporal's workflow sandbox. Workflow code imports .constants and .inputs
(which are lightweight dataclasses), and importing .client eagerly would
break sandbox validation. Import shared.temporal.client explicitly when
you need the client singleton.
"""

from .constants import Workflows, TaskQueues
from .inputs import (
    EnrollmentWorkflowInput,
    EnrollmentWorkflowOutput,
    CoursePublishWorkflowInput,
    CoursePublishWorkflowOutput,
)

__all__ = [
    "Workflows",
    "TaskQueues",
    "EnrollmentWorkflowInput",
    "EnrollmentWorkflowOutput",
    "CoursePublishWorkflowInput",
    "CoursePublishWorkflowOutput",
]
