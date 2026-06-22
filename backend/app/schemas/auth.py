"""Pydantic schemas for auth endpoints."""
import re
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: str = ""
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v):
        if v is None or v == "":
            return None
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if v:
            # Chinese mobile: 1[3-9]xxxxxxxxx
            if not re.match(r"^1[3-9]\d{9}$", v):
                raise ValueError("手机号格式不正确，请输入11位中国大陆手机号")
        return v


class LoginRequest(BaseModel):
    account: str  # email or phone
    password: str


class PasswordCheckRequest(BaseModel):
    password: str


class UpdateProfileRequest(BaseModel):
    nickname: str = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str = ""
    phone: str = ""
    nickname: str = ""
