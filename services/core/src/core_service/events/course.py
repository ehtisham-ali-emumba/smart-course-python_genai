from pydantic import BaseModel


class CourseCreatedPayload(BaseModel):
    course_id: int
    instructor_id: int
    title: str
    slug: str
    category: str | None = None


class CoursePublishedPayload(BaseModel):
    course_id: int
    instructor_id: int
    title: str
    published_at: str


class CourseUpdatedPayload(BaseModel):
    course_id: int
    instructor_id: int
    fields_changed: list[str]


class CourseArchivedPayload(BaseModel):
    course_id: int
    instructor_id: int
    title: str


class CourseDeletedPayload(BaseModel):
    course_id: int
    instructor_id: int
