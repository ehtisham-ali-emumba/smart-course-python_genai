from pydantic import BaseModel


class UserRegisteredPayload(BaseModel):
    user_id: int
    email: str
    role: str
    first_name: str
    last_name: str


class UserLoginPayload(BaseModel):
    user_id: int
    email: str


class UserProfileUpdatedPayload(BaseModel):
    user_id: int
    fields_changed: list[str]
