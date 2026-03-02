"""Shared HTTP client utility for Temporal activities."""

import logging
from typing import Any

import aiohttp
from aiohttp import ClientResponseError, ClientTimeout

from core_service.config import core_settings

logger = logging.getLogger(__name__)


def make_timeout() -> ClientTimeout:
    return ClientTimeout(total=core_settings.HTTP_TIMEOUT_SECONDS)


async def get_json(
    url: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Perform a GET request and return parsed JSON.
    Raises aiohttp.ClientResponseError on non-2xx.
    """
    async with aiohttp.ClientSession(timeout=make_timeout()) as session:
        async with session.get(url, headers=headers or {}) as resp:
            resp.raise_for_status()
            return await resp.json()


async def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Perform a POST request with JSON body and return parsed JSON.
    Raises aiohttp.ClientResponseError on non-2xx.
    """
    async with aiohttp.ClientSession(timeout=make_timeout()) as session:
        async with session.post(url, json=payload, headers=headers or {}) as resp:
            resp.raise_for_status()
            return await resp.json()
