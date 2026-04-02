import asyncio
from time import perf_counter
from typing import Any

import httpx

UPSTREAM_HEALTH_ENDPOINTS = {
    "user-service": "http://smartcourse-user-service:8001/health",
    "course-service": "http://smartcourse-course-service:8002/health",
    "notification-service": "http://smartcourse-notification-service:8005/health",
    "core-service": "http://smartcourse-core-service:8006/health",
    "analytics-service": "http://smartcourse-analytics-service:8007/health",
    "ai-service": "http://smartcourse-ai-service:8009/health",
}


async def _check_service_health(
    client: httpx.AsyncClient, service_name: str, health_url: str
) -> dict[str, Any]:
    start = perf_counter()
    try:
        response = await client.get(health_url)
        duration_ms = round((perf_counter() - start) * 1000, 2)
        is_healthy = 200 <= response.status_code < 300
        return {
            "service": service_name,
            "healthy": is_healthy,
            "status_code": response.status_code,
            "response_time_ms": duration_ms,
            "url": health_url,
            "error": None,
        }
    except httpx.TimeoutException:
        duration_ms = round((perf_counter() - start) * 1000, 2)
        return {
            "service": service_name,
            "healthy": False,
            "status_code": None,
            "response_time_ms": duration_ms,
            "url": health_url,
            "error": "timeout",
        }
    except httpx.HTTPError as exc:
        duration_ms = round((perf_counter() - start) * 1000, 2)
        return {
            "service": service_name,
            "healthy": False,
            "status_code": None,
            "response_time_ms": duration_ms,
            "url": health_url,
            "error": str(exc),
        }


async def build_gateway_health_report(timeout_seconds: float) -> dict[str, Any]:
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        checks = await asyncio.gather(
            *[
                _check_service_health(client, name, url)
                for name, url in UPSTREAM_HEALTH_ENDPOINTS.items()
            ]
        )

    services = {check["service"]: check for check in checks}
    all_healthy = all(check["healthy"] for check in checks)

    return {
        "status": "ok" if all_healthy else "degraded",
        "service": "api-gateway",
        "health_checked_by": "auth-sidecar",
        "all_services_healthy": all_healthy,
        "services": services,
    }
