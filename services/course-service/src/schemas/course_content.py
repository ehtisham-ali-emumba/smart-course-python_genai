from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ResourceSchema(BaseModel):
    """A single resource attached to a lesson."""
    name: str
    url: str
    type: str  # pdf, video, link, etc.


class LessonSchema(BaseModel):
    """A single lesson within a module."""
    lesson_id: int
    title: str
    type: str = Field(..., pattern=r"^(video|text|quiz|assignment)$")
    content: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: int
    is_preview: bool = False
    resources: list[ResourceSchema] = []


class ModuleSchema(BaseModel):
    """A single module containing lessons."""
    module_id: int
    title: str
    description: Optional[str] = None
    order: int
    is_published: bool = True
    lessons: list[LessonSchema] = []


class CourseContentMetadata(BaseModel):
    """Metadata stored alongside course content."""
    total_modules: int = 0
    total_lessons: int = 0
    total_duration_hours: Optional[float] = None
    tags: list[str] = []


class CourseContentCreate(BaseModel):
    """Schema for creating/replacing full course content."""
    modules: list[ModuleSchema] = []
    metadata: Optional[CourseContentMetadata] = None


class CourseContentResponse(BaseModel):
    """Schema for course content API responses."""
    course_id: int
    modules: list[ModuleSchema] = []
    metadata: Optional[CourseContentMetadata] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ModuleCreate(BaseModel):
    """Schema for adding a single module."""
    module_id: int
    title: str
    description: Optional[str] = None
    order: int
    is_published: bool = True
    lessons: list[LessonSchema] = []


class LessonCreate(BaseModel):
    """Schema for adding a single lesson to a module."""
    lesson_id: int
    title: str
    type: str = Field(..., pattern=r"^(video|text|quiz|assignment)$")
    content: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: int
    is_preview: bool = False
    resources: list[ResourceSchema] = []


class ModuleUpdate(BaseModel):
    """Schema for updating a module."""
    title: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None
    is_published: Optional[bool] = None


class LessonUpdate(BaseModel):
    """Schema for updating a lesson."""
    title: Optional[str] = None
    type: Optional[str] = Field(None, pattern=r"^(video|text|quiz|assignment)$")
    content: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: Optional[int] = None
    is_preview: Optional[bool] = None


class MediaResourceCreate(BaseModel):
    """Schema for adding media resources (video, pdf, audio, images)."""
    name: str
    url: str
    type: str = Field(..., pattern=r"^(video|pdf|audio|image|link)$")


class MediaResourceUpdate(BaseModel):
    """Schema for updating a media resource."""
    name: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = Field(None, pattern=r"^(video|pdf|audio|image|link)$")
