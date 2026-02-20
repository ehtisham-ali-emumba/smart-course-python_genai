from pydantic import BaseModel


class ProgressUpdatedPayload(BaseModel):
    user_id: int
    enrollment_id: int
    course_id: int
    item_type: str
    item_id: str
    progress_percentage: float


class CourseCompletedPayload(BaseModel):
    user_id: int
    enrollment_id: int
    course_id: int
