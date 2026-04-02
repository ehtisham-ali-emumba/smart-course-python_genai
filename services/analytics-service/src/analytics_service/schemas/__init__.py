from analytics_service.schemas.courses import CourseAnalyticsResponse, PopularCourseItem
from analytics_service.schemas.instructors import (
    InstructorAnalyticsResponse,
    InstructorLeaderboardItem,
)
from analytics_service.schemas.platform import (
    AIUsageTrendItem,
    PlatformOverviewResponse,
    PlatformTrendItem,
)
from analytics_service.schemas.students import StudentAnalyticsResponse

__all__ = [
    "PlatformOverviewResponse",
    "PlatformTrendItem",
    "AIUsageTrendItem",
    "CourseAnalyticsResponse",
    "PopularCourseItem",
    "InstructorAnalyticsResponse",
    "InstructorLeaderboardItem",
    "StudentAnalyticsResponse",
]
