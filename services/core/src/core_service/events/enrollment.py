from pydantic import BaseModel


class EnrollmentCreatedPayload(BaseModel):
    enrollment_id: int
    student_id: int
    course_id: int
    status: str = "active"


class EnrollmentDroppedPayload(BaseModel):
    enrollment_id: int
    student_id: int
    course_id: int


class EnrollmentReactivatedPayload(BaseModel):
    enrollment_id: int
    student_id: int
    course_id: int


class EnrollmentCompletedPayload(BaseModel):
    enrollment_id: int
    student_id: int
    course_id: int
    completed_at: str
