"""Datetime utilities."""

from datetime import datetime
from typing import Optional


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.utcnow()


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime to string."""
    return dt.strftime(fmt)


def parse_datetime(s: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> Optional[datetime]:
    """Parse datetime from string."""
    try:
        return datetime.strptime(s, fmt)
    except ValueError:
        return None
