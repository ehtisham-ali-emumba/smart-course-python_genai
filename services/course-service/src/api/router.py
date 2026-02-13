from fastapi import APIRouter

from api import certificates, course_content, courses, enrollments, progress

# Main API router
router = APIRouter()

router.include_router(courses.router, prefix="/courses", tags=["Courses"])
router.include_router(enrollments.router, prefix="/course/enrollments", tags=["Enrollments"])
router.include_router(certificates.router, prefix="/course/certificates", tags=["Certificates"])
router.include_router(course_content.router, prefix="/courses", tags=["Course Content"])
router.include_router(progress.router, prefix="/course/progress", tags=["Progress"])
