"""Pydantic schemas for auth endpoints."""
import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: str = ""
    password: str
    nickname: str = ""

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

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: str) -> str:
        """Optional nickname (2-20 chars). Empty string means 'auto-generate'."""
        if v:
            v = v.strip()
            if len(v) < 2 or len(v) > 20:
                raise ValueError("昵称长度需为2-20个字符")
        return v


class LoginRequest(BaseModel):
    account: str  # email or phone
    password: str


class PasswordCheckRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


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
