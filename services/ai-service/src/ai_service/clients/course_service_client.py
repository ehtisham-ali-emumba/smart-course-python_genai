"""HTTP client for communicating with course-service."""

import httpx
import structlog
from ai_service.config import settings

logger = structlog.get_logger(__name__)


class CourseServiceClient:
    """Client for persisting generated content to course-service."""

    def __init__(self):
        self.base_url = settings.COURSE_SERVICE_URL

    async def save_summary(
        self,
        course_id: int,
        module_id: str,
        payload: dict,
        user_id: int,
    ) -> dict | None:
        """Save a summary to course-service via POST or PUT.

        Args:
            course_id: Course ID
            module_id: Module ID
            payload: Summary creation payload
            user_id: User ID for authorization headers

        Returns:
            Response JSON on success, None on failure
        """
        url = f"{self.base_url}/courses/{course_id}/modules/{module_id}/summary"
        headers = {"X-User-ID": str(user_id), "X-User-Role": "instructor"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Try POST first
                resp = await client.post(url, json=payload, headers=headers)

                # If 409 Conflict, try PUT instead
                if resp.status_code == 409:
                    resp = await client.put(url, json=payload, headers=headers)

                resp.raise_for_status()
                return resp.json()

            except httpx.HTTPError as e:
                logger.error(
                    "Failed to save summary",
                    error=str(e),
                    course_id=course_id,
                    module_id=module_id,
                )
                return None

    async def save_quiz(
        self,
        course_id: int,
        module_id: str,
        payload: dict,
        user_id: int,
    ) -> dict | None:
        """Save a quiz to course-service via POST or PUT.

        Args:
            course_id: Course ID
            module_id: Module ID
            payload: Quiz creation payload
            user_id: User ID for authorization headers

        Returns:
            Response JSON on success, None on failure
        """
        url = f"{self.base_url}/courses/{course_id}/modules/{module_id}/quiz"
        headers = {"X-User-ID": str(user_id), "X-User-Role": "instructor"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Try POST first
                resp = await client.post(url, json=payload, headers=headers)

                # If 409 Conflict, try PUT instead
                if resp.status_code == 409:
                    resp = await client.put(url, json=payload, headers=headers)

                resp.raise_for_status()
                return resp.json()

            except httpx.HTTPError as e:
                logger.error(
                    "Failed to save quiz",
                    error=str(e),
                    course_id=course_id,
                    module_id=module_id,
                )
                return None

    async def get_course(self, course_id: int, user_id: int) -> dict | None:
        """Validate instructor ownership of a single course via course-service.

        Hits the instructor-scoped endpoint so the course-service enforces
        ownership: a 404 is returned both when the course does not exist and
        when it exists but belongs to a different instructor.

        Args:
            course_id: Course ID to look up
            user_id: Instructor user ID (sent as X-User-ID header)

        Returns:
            Course dict (includes instructor_id) on success, None if not found,
            not owned, or on error
        """
        url = f"{self.base_url}/courses/my-courses/{course_id}"
        headers = {"X-User-ID": str(user_id), "X-User-Role": "instructor"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()

            except httpx.HTTPError as e:
                logger.error(
                    "Failed to fetch course",
                    error=str(e),
                    course_id=course_id,
                )
                return None
