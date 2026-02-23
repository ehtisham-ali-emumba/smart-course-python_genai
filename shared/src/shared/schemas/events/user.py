"""User event schemas."""

from pydantic import BaseModel


class UserRegisteredPayload(BaseModel):
    """Payload for user.registered event."""

    user_id: int
    email: str
    first_name: str
    last_name: str


class UserLoginPayload(BaseModel):
    """Payload for user.login event."""

    user_id: int
    email: str


class UserProfileUpdatedPayload(BaseModel):
    """Payload for user.profile_updated event."""

    user_id: int
    fields_changed: list[str]
