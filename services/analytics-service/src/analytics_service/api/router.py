from fastapi import APIRouter

from analytics_service.api import courses, instructors, platform, students

router = APIRouter(prefix="/analytics")

router.include_router(platform.router, tags=["Analytics Platform"])
router.include_router(courses.router, tags=["Analytics Courses"])
router.include_router(instructors.router, tags=["Analytics Instructors"])
router.include_router(students.router, tags=["Analytics Students"])
