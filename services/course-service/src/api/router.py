from fastapi import APIRouter

from api import (
    certificates,
    course_content,
    courses,
    enrollments,
    module_quiz,
    progress,
    quiz_attempt,
    module_summary,
)

# Main API router
router = APIRouter()

router.include_router(courses.router, prefix="/courses", tags=["Courses"])
router.include_router(enrollments.router, prefix="/course/enrollments", tags=["Enrollments"])
router.include_router(certificates.router, prefix="/course/certificates", tags=["Certificates"])
router.include_router(course_content.router, prefix="/courses", tags=["Course Content"])
router.include_router(progress.router, prefix="/course/progress", tags=["Progress"])
router.include_router(module_quiz.router, prefix="/courses", tags=["Module Quiz"])
router.include_router(quiz_attempt.router, prefix="/courses", tags=["Quiz Attempts"])
router.include_router(module_summary.router, prefix="/courses", tags=["Module Summary"])
