import json
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as redis


async def get_or_set_json(
    client: redis.Redis | None,
    key: str,
    ttl_seconds: int,
    loader: Callable[[], Awaitable[Any]],
) -> Any:
    if client is None:
        return await loader()

    cached = await client.get(key)
    if cached:
        return json.loads(cached)

    data = await loader()
    await client.setex(key, ttl_seconds, json.dumps(data, default=str))
    return data


async def delete_by_patterns(client: redis.Redis | None, patterns: list[str]) -> None:
    if client is None:
        return

    for pattern in patterns:
        keys = await client.keys(pattern)
        if keys:
            await client.delete(*keys)
