"""Common exceptions."""

from fastapi import HTTPException


class NotFoundError(HTTPException):
    """Resource not found."""

    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=404, detail=detail)


class BadRequestError(HTTPException):
    """Bad request."""

    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=400, detail=detail)
