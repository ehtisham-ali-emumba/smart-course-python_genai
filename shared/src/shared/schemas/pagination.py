"""Pagination schema."""

from pydantic import BaseModel


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = 1
    size: int = 10

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size
