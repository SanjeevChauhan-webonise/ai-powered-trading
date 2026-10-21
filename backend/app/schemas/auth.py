from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["beginner", "advanced", "expert"]
_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    email: str = Field(pattern=_EMAIL, max_length=254)
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    level: Level = "beginner"


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    level: Level | None = None


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    level: Level


class TokenOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut
